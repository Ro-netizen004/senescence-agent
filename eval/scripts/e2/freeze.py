"""Freeze E2 after outcome-free tests and integrity checks, before case generation."""
import subprocess
import sys
from common import *
from reporters import PROMPTS,REQUEST,MODEL_CONFIG
from validate import validate

def main():
    assert not (OUT/'execution').exists() and not (OUT/'E2_PROTOCOL_LOCK.json').exists()
    assert read(OUT/'MODEL_ENVIRONMENT_NETWORK_RECHECK.json')['status']=='PASS'
    preservation();validate()
    textfile(OUT/'E2_BASELINE_PROMPTS.md','# Frozen E2 baseline prompts\n\n## Common user request\n\n'+REQUEST+
        '\n\n## Arm A system instruction\n\n'+PROMPTS['A']+'\n\n## Arm B system instruction\n\n'+PROMPTS['B']+
        '\n\n## Shared model configuration\n\n'+encode(MODEL_CONFIG)+'\nModel: '+MODEL+'\n')
    commands=[
        [sys.executable,'-m','unittest','discover','-s','eval/scripts/e2','-p','test_e2.py'],
        [sys.executable,'-m','unittest','-v','backend/tests/test_output_firewall.py','backend/tests/test_inference_state.py',
         'backend/tests/test_admissibility_confounding.py','backend/tests/test_admissibility_replicates.py',
         'backend/tests/test_governance_method_parity.py','backend/tests/test_governance_guard.py']]
    for i,cmd in enumerate(commands):
        result=subprocess.run(cmd,cwd=ROOT,capture_output=True,text=True)
        textfile(OUT/f'PRELOCK_TESTS_{i+1}.txt','COMMAND: '+' '.join(cmd)+'\n'+result.stdout+result.stderr)
        assert result.returncode==0, 'Tests failed before freeze'
    files={rel(p):sha(p) for p in sorted((ROOT/'eval/scripts/e2').glob('*.py'))}
    for p in OUT.rglob('*'):
        if p.is_file() and not any(part.startswith('prelock_') for part in p.parts):files[rel(p)]=sha(p)
    source=read(OUT/'E2_SOURCE_MANIFEST.json');files.update(source)
    for name in ['admissibility.py','inference_state.py','output_schema.py','output_renderer.py','design_validation.py','governance.py']:
        p=ROOT/'backend/agent'/name;files[rel(p)]=sha(p)
    p=ROOT/'backend/tools/run_deseq2.py';files[rel(p)]=sha(p)
    p=E1/'E1_INDEPENDENT_CLAIM_CRITERIA_V1.md';files[rel(p)]=sha(p)
    write(OUT/'E2_PROTOCOL_LOCK.json',{'status':'FROZEN','timestamp_utc':now(),
        'scored_case_responses_before_lock':0,'scoring_before_lock':False,'files':files,
        'user_authorized_adapter':'e2_reporting_interface_v1','source_outcomes_previously_known':True})
    print(encode({'status':'FROZEN','files':len(files),'protocol_sha256':sha(OUT/'E2_PROTOCOL.md'),
                  'lock_sha256':sha(OUT/'E2_PROTOCOL_LOCK.json')}))

if __name__=='__main__':main()
