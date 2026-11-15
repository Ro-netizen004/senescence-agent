"""Prospective E2 3.6 interface. No client creation, network calls, or CLI execution.

Pure request routing is tested on all real inputs. Report rendering and SDK-call
boundary tests use synthetic fixtures only. A separately approved launch is required.
"""
import copy
from common import ROOT, OUT, read, sha, digest
from privacy_export import DEST as EXPORT, local_d_input, policy_signature
from reporters import template, firewall

DEST = ROOT / 'eval/results/v2/e2/e2_model36_amendment_v1_20261024_01'
MODEL = 'gemini-3.6-flash'
PRIVACY_LOCK = '8113a975ada9aa4a2352a79241c6f9ed849805a4ad9afaec8d946130c8757d0a'
CONFIG = {
    'requested_model': MODEL, 'expected_returned_model': MODEL,
    'temperature': 0, 'max_output_tokens': 4096,
    'thinking': 'provider default (omitted, unchanged)',
    'tools': 'none', 'timeout_ms': 120000, 'sdk_attempts': 1,
    'application_retries': 0, 'max_concurrent_jobs': 2,
    'dispatch_seed': 20261023, 'max_api_calls': 204, 'planned_slots': 408,
    'automatic_resume': False, 'fallback': False,
    'stop': '401/403 or three consecutive API failures/empty responses; finish dispatched batch',
    'model_mismatch': 'preserve response as MODEL_MISMATCH; halt after current batch; never replace',
    'service': 'Gemini Developer API Standard Paid Services; not Contributor/Batch/Flex',
    'project_quota': 'NOT_VERIFIED; launch blocked until documented project RPM/TPM/RPD and headroom are checked',
}


def verify_export():
    if sha(EXPORT / 'EXPORT_SPEC_LOCK.json') != PRIVACY_LOCK:
        raise ValueError('Privacy lock mismatch')
    lock = read(EXPORT / 'EXPORT_SPEC_LOCK.json')
    for p, h in lock['files'].items():
        if sha(ROOT / p) != h:
            raise ValueError('Frozen export file mismatch')
    return lock


def amended_request(original):
    if set(original) != {'model', 'contents', 'config'} or original['model'] != 'gemini-3.5-flash':
        raise ValueError('Unexpected frozen request')
    req = copy.deepcopy(original)
    req['model'] = MODEL
    return req


def route(record, arm):
    """Inspect only. Caller verifies locks once before loading the fixed frame."""
    if arm not in ('A', 'B', 'C', 'D'):
        raise ValueError('Unknown arm')
    packet_path = EXPORT / record['packet_file']
    if sha(packet_path) != record['sanitized_packet_sha256']:
        raise ValueError('Packet mismatch')
    packet = read(packet_path)
    if digest(packet) != record['sanitized_content_sha256']:
        raise ValueError('Content mismatch')
    routed = {'packet': packet, 'request': None, 'private': None,
              'canonical_sha256': record['original_packet_sha256'],
              'packet_sha256': sha(packet_path), 'packet_content_sha256': digest(packet),
              'gate_signature': record['gate_signature']}
    if arm in ('A', 'B'):
        source = record['requests'][arm]
        if sha(EXPORT / source['file']) != source['sha256']:
            raise ValueError('Request mismatch')
        routed['request'] = amended_request(read(EXPORT / source['file']))
    if arm == 'D':
        original_private = read(OUT / 'arm_d_inputs' / (record['source_case'] + '.json'))
        routed['private'] = local_d_input(packet, original_private)
        if policy_signature(routed['private']) != record['gate_signature']:
            raise ValueError('Gate mismatch')
    return routed


def sdk_arguments(request):
    """Exact request boundary. No metadata, licenses or local mappings added."""
    from google.genai import types
    if set(request) != {'model', 'contents', 'config'} or request['model'] != MODEL:
        raise ValueError('Unexpected request/model')
    return {'model': MODEL, 'contents': request['contents'],
            'config': types.GenerateContentConfig(**request['config'])}


def response_status(response):
    # Record requested ID separately from actual returned backend; fail closed.
    if response.model_version != MODEL:
        return 'MODEL_MISMATCH'
    if any('MAX_TOKENS' in str(c.finish_reason) for c in response.candidates or []):
        return 'TRUNCATED_RESPONSE'
    return 'SUCCESS' if (response.text or '').strip() else 'EMPTY_RESPONSE'


def local_report(arm, packet, private=None):
    if arm == 'C':
        return template(packet), None
    if arm == 'D':
        return firewall(packet, private)
    raise ValueError('Only local arms')


def require_clearance(receipt, protocol_hash):
    """Receipt must be created only from separately reviewed human authorization.

    This does not generate/approve receipts or infer permission from API success.
    No valid receipt is present or produced during amendment preparation.
    """
    required = ('billing_link_verified', 'data_authorization_verified',
                'quota_headroom_verified', 'explicit_final_execution_approval')
    if (not receipt or receipt.get('protocol_sha256') != protocol_hash or
            any(receipt.get(k) is not True for k in required)):
        raise PermissionError('E2_BLOCKED: separately verified execution clearance required')


if __name__ == '__main__':
    raise SystemExit('PREPARATION_ONLY: no execution entrypoint; E2 remains blocked')
