"""E2 reporting-interface V1. No changes to production policy or numerical inputs."""
import copy
from agent.inference_state import apply_inference_state
from agent.output_renderer import render_tool_calls_with_schema
from common import digest

VERSION='e2_reporting_interface_v1'

def render(packet,private):
    from reporters import metadata,table
    tool=copy.deepcopy(private['tool'])
    assert tool['results']==packet['statistics']['rows']
    before=digest(packet)
    result=apply_inference_state('run_deseq2',tool,private['args'])
    original,schemas=render_tool_calls_with_schema([{'name':'run_deseq2','args':private['args'],'result':result}])
    schema=schemas[0]
    blocked=schema.get('allowed_interpretation_level')=='BLOCKED' or schema.get('inference_state')=='BLOCKED'
    withheld=bool(schema.get('result_withheld'))
    supplement=('Additional evidence is retained internally; blocked inference permissions are unchanged.' if blocked
                else metadata(packet,include_identity=not withheld))
    if not withheld and not blocked:supplement+='\n\n'+table(packet)
    assert before==digest(packet)
    return original+'\n\n'+supplement,{'original_schema':schema,'original_rendered_body':original,
        'inference_state':result['inference_state'],'gate1_replay_mode':private['gate1_mode'],
        'adapter':VERSION,'canonical_context_complete':True,'canonical_content_sha256':before,
        'adapter_transformation':'Original body verbatim; contextual metadata appended unless blocked; identity and gene-result supplements suppressed on withholding; no sensitivity input changes license'}
