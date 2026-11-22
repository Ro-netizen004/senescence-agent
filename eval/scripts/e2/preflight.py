"""Non-scientific access and public environment checks, no dataset analysis."""
import os
import subprocess
import sys
from google import genai
from google.genai import types
from common import ROOT,OUT,MODEL,write,now,textfile,preservation

def main():
    access_retry='--network-recheck' in sys.argv
    if not access_retry:
        OUT.mkdir(parents=True,exist_ok=False)
        write(OUT/'SOURCE_PRESERVATION_BEFORE.json',preservation())
    freeze=subprocess.check_output([sys.executable,'-m','pip','freeze','--all'],text=True,stderr=subprocess.DEVNULL)
    if not access_retry: textfile(OUT/'ENVIRONMENT_FREEZE.txt',freeze)
    pip=subprocess.run([sys.executable,'-m','pip','check'],capture_output=True,text=True)
    record={'time_utc':now(),'python':sys.version.split()[0],'executable':sys.executable,
        'git_revision':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        'pip_check_returncode':pip.returncode,'pip_check_output':pip.stdout,
        'package_freeze_matches':set(freeze.splitlines())==set((ROOT/'TASK2_PIP_FREEZE.txt').read_text().splitlines()),
        'model':os.getenv('GEMINI_MODEL'),'report_overrides_present':bool(os.getenv('REPORT_MODEL') or os.getenv('REPORT_GEMINI_API_KEY')),
        'credential_present':bool(os.getenv('GEMINI_API_KEY')),'non_scientific':True,'api_calls':0,
        'scientific_data_sent':False,'status':'PREFLIGHT_BLOCKED'}
    if (record['python']=='3.11.9' and record['package_freeze_matches'] and pip.returncode==0
        and record['model']==MODEL and not record['report_overrides_present'] and record['credential_present']):
        client=genai.Client(api_key=os.getenv('GEMINI_API_KEY'),http_options=types.HttpOptions(
            timeout=30000,retry_options=types.HttpRetryOptions(attempts=1)))
        try:
            record['api_calls']=1
            response=client.models.get(model=MODEL)
            record['status']='PASS' if response else 'EMPTY_RESPONSE'
        except Exception as e:
            record['error_type']=type(e).__name__
            code=getattr(e,'code',None)
            record['api_error_code']=code if isinstance(code,int) else None
        finally: client.close()
    write(OUT/('MODEL_ENVIRONMENT_NETWORK_RECHECK.json' if access_retry else 'MODEL_ENVIRONMENT_PREFLIGHT.json'),record)
    print(record)

if __name__=='__main__': main()
