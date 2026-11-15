"""Single registered E2 generation. Exclusive reservations; no automatic resume/retry."""
import concurrent.futures
import os
import time
import threading
from google import genai
from google.genai import types
from common import *
from reporters import PROMPTS,REQUEST,MODEL_CONFIG,ADAPTER_VERSION,template,firewall

def run(item):
    case,arm=item['case_id'],item['arm'];path=OUT/'execution'/f'{case}_{arm}'
    path.mkdir(exist_ok=False)
    packet=read(OUT/f'packets/{case}.json');h=sha(OUT/f'packets/{case}.json')
    write(path/'STARTED.json',{'time':now(),'case_id':case,'arm':arm,'packet_sha256':h})
    write(path/'REPORTER_VISIBLE_PACKET.json',packet)
    rec={'case_id':case,'arm':arm,'packet_sha256':h,'actual_input_digest':digest(packet),
         'reporter_visible_packet_sha256':sha(path/'REPORTER_VISIBLE_PACKET.json'),
         'adapter_version':ADAPTER_VERSION if arm=='D' else 'canonical_identity_transform_v1',
         'gate_state':None,'time_start':now(),'api_calls':0,'retries':0,'status':'EXECUTION_FAILURE','text':''}
    assert rec['reporter_visible_packet_sha256']==h
    start=time.monotonic()
    try:
        if arm in 'AB':
            full=REQUEST+'\n\nCANONICAL EVIDENCE:\n'+encode(packet)
            write(path/'REQUEST.json',{'system_instruction':PROMPTS[arm],'contents':full,
                'model':MODEL,'config':MODEL_CONFIG,'packet_sha256':h})
            client=genai.Client(api_key=os.getenv('GEMINI_API_KEY'),http_options=types.HttpOptions(
                timeout=120000,retry_options=types.HttpRetryOptions(attempts=1)))
            try:
                rec['api_calls']=1
                response=client.models.generate_content(model=MODEL,contents=full,
                    config=types.GenerateContentConfig(system_instruction=PROMPTS[arm],**MODEL_CONFIG))
                rec['text']=response.text or ''
                rec['model_version']=response.model_version
                rec['usage']=response.usage_metadata.model_dump(mode='json') if response.usage_metadata else None
                rec['finish_reasons']=[str(c.finish_reason) for c in response.candidates or []]
                rec['provider_candidates']=[c.model_dump(mode='json') for c in response.candidates or []]
                rec['status']='SUCCESS' if rec['text'].strip() else 'EMPTY_RESPONSE'
                if any('MAX_TOKENS' in reason for reason in rec['finish_reasons']):rec['status']='TRUNCATED_RESPONSE'
            finally:client.close()
        elif arm=='C':
            write(path/'REQUEST.json',{'implementation':'reporters.template','model_input':None,'canonical_packet_sha256':h})
            rec.update(text=template(packet),status='SUCCESS')
        else:
            text,trace=firewall(packet,read(OUT/f'arm_d_inputs/{case}.json'))
            write(path/'REQUEST.json',{'implementation':'reporters.firewall','model_input':None,'canonical_packet_sha256':h,
                'frozen_gate_input_sha256':sha(OUT/f'arm_d_inputs/{case}.json'),'adapter_transformation':trace['adapter_transformation']})
            rec['gate_state']=trace['inference_state']
            write(path/'GOVERNANCE_TRACE.json',trace);rec.update(text=text,status='SUCCESS')
    except Exception as e:
        rec['status']='API_FAILURE' if rec['api_calls'] else 'EXECUTION_FAILURE'
        rec['error_type']=type(e).__name__;code=getattr(e,'code',None)
        rec['api_error_code']=code if isinstance(code,int) else None
        # No exception bodies, request headers or private credential logging.
    rec['seconds']=time.monotonic()-start;rec['time_end']=now()
    write(path/'RESPONSE.json',rec)
    return rec

def main():
    verify_lock();preservation()
    assert os.getenv('GEMINI_MODEL')==MODEL and os.getenv('GEMINI_API_KEY')
    assert not os.getenv('REPORT_MODEL') and not os.getenv('REPORT_GEMINI_API_KEY')
    (OUT/'execution').mkdir(exist_ok=False)
    write(OUT/'EXECUTION_STARTED.json',{'timestamp':now(),'protocol_lock_sha256':sha(OUT/'E2_PROTOCOL_LOCK.json')})
    order=read(OUT/'E2_EXECUTION_ORDER.json')['order'];done=0;consecutive_api=0;halt=None
    # Two registered jobs per batch, preserves seeded dispatch order. No resubmission.
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        for index in range(0,len(order),2):
            results=list(pool.map(run,order[index:index+2]))
            for r in results:
                done+=1
                if r['api_calls']:
                    consecutive_api=consecutive_api+1 if r['status'] in ['API_FAILURE','EMPTY_RESPONSE'] else 0
                if r.get('api_error_code') in [401,403]:halt='AUTHENTICATION_OR_PERMISSION_FAILURE'
                if consecutive_api>=3:halt='THREE_CONSECUTIVE_API_FAILURES'
            print(encode({'completed_slots':done,'total_slots':408,'last':[(r['case_id'],r['arm'],r['status']) for r in results]}),flush=True)
            if halt:break
    write(OUT/'EXECUTION_STOPPED.json',{'timestamp':now(),'completed_slots':done,'planned_slots':408,
        'reason':halt or 'FRAME_COMPLETE','registered_retries':0})

if __name__=='__main__':main()
