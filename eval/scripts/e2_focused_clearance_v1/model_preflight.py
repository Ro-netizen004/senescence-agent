"""One literal nonresearch direct-model preflight. No research input reads."""
import json
import logging
import os
from pathlib import Path
from datetime import datetime, timezone
logging.disable(logging.CRITICAL)

def main():
    from google import genai
    from google.genai import types
    dest = Path(__file__).resolve().parents[3] / 'eval/results/v2/e2/e2_focused_clearance_v1_20261024_01/direct_model_preflight'
    dest.mkdir(exist_ok=False)
    def save(name, value):
        with (dest / name).open('x') as f: json.dump(value, f, indent=2)
    rec = {'classification':'SYNTHETIC_ONLY_NOT_SCORED', 'time':datetime.now(timezone.utc).isoformat(),
           'key_present':bool(os.getenv('GEMINI_API_KEY')), 'requested_model':'gemini-3.6-flash',
           'attempts':0,'retries':0,'research_inputs_read':0,'status':'PREFLIGHT_BLOCKED'}
    if not rec['key_present'] or any(os.getenv(k) for k in ['GOOGLE_API_KEY','REPORT_MODEL','REPORT_GEMINI_API_KEY','GOOGLE_GENAI_USE_VERTEXAI','GOOGLE_GEMINI_BASE_URL','GOOGLE_VERTEX_BASE_URL','HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','http_proxy','https_proxy','all_proxy']):
        save('RESULT.json', rec); print(json.dumps(rec)); return
    req = {'model':'gemini-3.6-flash','contents':'This is a non-research connectivity check. Reply only OK.',
           'config':{'temperature':0,'max_output_tokens':4096}}
    save('REQUEST.json',req)
    client = None
    try:
        client = genai.Client(api_key=os.getenv('GEMINI_API_KEY'),http_options=types.HttpOptions(timeout=120000,retry_options=types.HttpRetryOptions(attempts=1)))
        rec['attempts']=1
        response=client.models.generate_content(model=req['model'],contents=req['contents'],config=types.GenerateContentConfig(**req['config']))
        rec['actual_model']=response.model_version
        rec['ok_reply']=(response.text or '').strip()=='OK'
        rec['usage']={k:getattr(response.usage_metadata,k,None) for k in ['prompt_token_count','candidates_token_count','thoughts_token_count','total_token_count']}
        rec['status']='PASS' if response.model_version==req['model'] and rec['ok_reply'] else 'PREFLIGHT_BLOCKED'
    except Exception as e:
        rec['error_type']=type(e).__name__; c=getattr(e,'code',None)
        rec['api_error_code']=c if isinstance(c,int) else None
    finally:
        if client:
            try:client.close()
            except Exception:rec['close_failure']=True
        save('RESULT.json',rec)
    print(json.dumps(rec))

if __name__=='__main__':main()
