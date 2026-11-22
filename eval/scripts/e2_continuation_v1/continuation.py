"""Prospective E2 continuation: only slots undispatched in sealed attempt one.

Preparation and validation are offline. Only live() can transmit requests, and it
requires a separate exact clearance. No automatic resume or retry exists.
"""
import json
import os
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from common import ROOT, read, sha, write, now
from integration import DEST as AMENDMENT, MODEL, route
from privacy_export import DEST as EXPORT
from orchestrator import (planning_tokens, price, run_frame, send_gemini, seal,
                          verify_amendment, verify_manifest)

BASE = ROOT / 'eval/results/v2/e2'
ORIGINAL = BASE / 'e2_gemini36_execution_v1_20261024_01'
ORIGINAL_ANALYSIS = BASE / 'e2_gemini36_analysis_v1_20261024_01'
PREP = BASE / 'e2_continuation_protocol_v1_20261025_01'
SCRIPT = Path(__file__).resolve()
EXPECTED_ORIGINAL_MANIFEST = '600626974e7fafa50bb993de3d2f1935b1bb527d82ef50ddd45bea7d1f85d353'
EXPECTED_ANALYSIS_MANIFEST = '78bc3fa57c70f2ad61a2be06cc426ee0156d30880ea9d1a3868d46fa8d0fe601'
EXPECTED_AMENDMENT = '85138909eebd21b1abfa7995a1474bcc634404bad1dd96e310f450e0ffaa60be'
EXPECTED_AMENDMENT_LOCK = 'd4092071e8a72c74b3ca6af9882e896c37c65b60ce69a6ca88de2b3afb89027a'


def select_pending(order, attempted, missing):
    """Pure selection from the original immutable dispatch order and ledger."""
    keys = [(x['case_id'], x['arm']) for x in order]
    if len(keys) != 408 or len(set(keys)) != 408:
        raise ValueError('Original 408-slot frame changed')
    attempted = set(attempted)
    missing_keys = [(x['case_id'], x['arm']) for x in missing]
    if len(missing_keys) != len(set(missing_keys)) or any(x.get('status') != 'NOT_DISPATCHED' for x in missing):
        raise ValueError('Original missing ledger is not exclusively undispatched')
    if attempted & set(missing_keys):
        raise ValueError('An attempted slot would be resubmitted')
    if attempted | set(missing_keys) != set(keys):
        raise ValueError('Attempted/pending partition does not equal frozen frame')
    selected = [x for x in order if (x['case_id'], x['arm']) in set(missing_keys)]
    if [(x['case_id'], x['arm']) for x in selected] != missing_keys:
        raise ValueError('Pending order differs from original seeded order')
    return selected


def calculate_pending():
    verify_amendment()
    verify_manifest(ORIGINAL)
    verify_manifest(ORIGINAL_ANALYSIS)
    if sha(ORIGINAL / 'SHA256_MANIFEST.json') != EXPECTED_ORIGINAL_MANIFEST:
        raise ValueError('Original execution manifest changed')
    if sha(ORIGINAL_ANALYSIS / 'SHA256_MANIFEST.json') != EXPECTED_ANALYSIS_MANIFEST:
        raise ValueError('Original analysis manifest changed')
    if sha(AMENDMENT / 'E2_MODEL_AMENDMENT_V1.md') != EXPECTED_AMENDMENT:
        raise ValueError('Frozen model protocol changed')
    if sha(AMENDMENT / 'AMENDMENT_LOCK.json') != EXPECTED_AMENDMENT_LOCK:
        raise ValueError('Frozen amendment lock changed')
    summary = read(ORIGINAL / 'SUMMARY.json')
    if (summary['status'], summary['reason'], summary['completed_slots'], summary['api_attempts'], summary['retries']) != (
            'E2_PARTIAL', 'QUOTA_WINDOW_CHANGED', 156, 86, 0):
        raise ValueError('Original execution classification changed')
    order = read(ORIGINAL / 'STARTED.json')['order']
    attempted = {}
    for x in order:
        slot = ORIGINAL / f"{x['case_id']}_{x['arm']}"
        if slot.exists():
            verify_manifest(slot)
            rec = read(slot / 'RESPONSE.json')
            if (rec['case_id'], rec['arm']) != (x['case_id'], x['arm']):
                raise ValueError('Original slot identity changed')
            attempted[(x['case_id'], x['arm'])] = rec['status']
    if len(attempted) != 156 or Counter(attempted.values()) != Counter(
            {'SUCCESS': 152, 'API_FAILURE': 2, 'TRUNCATED_RESPONSE': 2}):
        raise ValueError('Original attempted slots changed')
    pending = select_pending(order, attempted, summary['incomplete'])
    if len(pending) != 252 or Counter(x['arm'] for x in pending) != Counter(
            {'A': 53, 'B': 65, 'C': 68, 'D': 66}):
        raise ValueError('Pending slot counts changed')
    ledger = {x['source_case']: x for x in read(EXPORT / 'local_only/CASE_TRANSFER_LEDGER.json')}
    entries = []
    for x in pending:
        record = ledger[x['case_id']]
        routed = route(record, x['arm'])
        row = {'case_id': x['case_id'], 'arm': x['arm'],
               'canonical_packet_sha256': record['original_packet_sha256'],
               'sanitized_packet_sha256': record['sanitized_packet_sha256'],
               'gate_signature': record['gate_signature']}
        if x['arm'] in 'AB':
            request = AMENDMENT / 'requests' / (record['export_case'] + '_' + x['arm'] + '.json')
            if read(request) != routed['request']:
                raise ValueError('Frozen request does not match routed packet')
            row['request_sha256'] = sha(request)
            row['planning_tokens'] = planning_tokens(routed['request'])
        entries.append(row)
    if sum(x['arm'] in 'AB' for x in entries) != 118:
        raise ValueError('Expected 118 remaining model calls')
    return {'classification': 'E2_UNDISPATCHED_ONLY_CONTINUATION',
            'original_execution_manifest_sha256': EXPECTED_ORIGINAL_MANIFEST,
            'original_analysis_manifest_sha256': EXPECTED_ANALYSIS_MANIFEST,
            'original_execution_summary_sha256': sha(ORIGINAL / 'SUMMARY.json'),
            'original_seeded_order_sha256': sha(AMENDMENT / 'EXECUTION_ORDER.json'),
            'amendment_protocol_sha256': EXPECTED_AMENDMENT,
            'amendment_lock_sha256': EXPECTED_AMENDMENT_LOCK,
            'pending_count': 252, 'pending_api_calls': 118,
            'pending_local_slots': 134, 'pending_by_arm': dict(Counter(x['arm'] for x in entries)),
            'pending_by_family': dict(Counter(x['case_id'].split('_')[0] for x in entries)),
            'prior_attempted_count': 156, 'prior_non_success_count': 4,
            'entries': entries}


def freeze():
    if not (PREP / 'CONTINUATION_PROTOCOL.md').is_file():
        raise ValueError('Prospective protocol must exist before freeze')
    payload = calculate_pending()
    write(PREP / 'PENDING_SLOTS.json', payload)
    write(PREP / 'FREEZE_RECORD.json', {
        'frozen_utc': now(), 'protocol_sha256': sha(PREP / 'CONTINUATION_PROTOCOL.md'),
        'pending_sha256': sha(PREP / 'PENDING_SLOTS.json'), 'runner_sha256': sha(SCRIPT),
        'source_execution_manifest_sha256': EXPECTED_ORIGINAL_MANIFEST,
        'source_analysis_manifest_sha256': EXPECTED_ANALYSIS_MANIFEST})
    return seal(PREP)


def verify_frozen():
    verify_manifest(PREP)
    record = read(PREP / 'FREEZE_RECORD.json')
    if record['runner_sha256'] != sha(SCRIPT) or record['protocol_sha256'] != sha(PREP / 'CONTINUATION_PROTOCOL.md'):
        raise ValueError('Continuation implementation/protocol changed')
    if record['pending_sha256'] != sha(PREP / 'PENDING_SLOTS.json'):
        raise ValueError('Pending manifest changed')
    if read(PREP / 'PENDING_SLOTS.json') != calculate_pending():
        raise ValueError('Pending manifest no longer equals original ledger')
    return read(PREP / 'PENDING_SLOTS.json')


def validate_clearance(receipt, manifest):
    required = ['billing_link_verified', 'quota_new_window_verified',
                'project_credit_sufficient', 'backend_route_verified',
                'transfer_authorization_still_applicable', 'explicit_user_continuation_authorization']
    if any(receipt.get(x) is not True for x in required):
        raise PermissionError('Current-window continuation clearance incomplete')
    if receipt.get('model') != MODEL or receipt.get('project_id') != 'gen-lang-client-0924718643':
        raise PermissionError('Model/project changed')
    if receipt.get('pending_manifest_sha256') != sha(PREP / 'PENDING_SLOTS.json') or receipt.get('protocol_sha256') != sha(PREP / 'CONTINUATION_PROTOCOL.md'):
        raise PermissionError('Wrong pending/protocol identity')
    if receipt.get('max_scored_api_calls') != 118 or receipt.get('budget_usd') != 3.9:
        raise PermissionError('Wrong continuation cap/budget')
    if receipt.get('rpd_remaining', 0) < 118 or receipt.get('rpm_available', 0) < 2 or receipt.get('tpm_available', 0) < 41422:
        raise PermissionError('Insufficient quota headroom')
    if datetime.now(timezone.utc) >= datetime.fromisoformat(receipt['expires_utc']):
        raise PermissionError('Continuation clearance expired')
    prior_pt = datetime.fromisoformat(read(ORIGINAL / 'STARTED.json')['time']).astimezone(ZoneInfo('America/Los_Angeles')).date()
    now_pt = datetime.now(ZoneInfo('America/Los_Angeles'))
    if now_pt.date() <= prior_pt:
        raise PermissionError('New quota day has not begun')
    # The original 61s cadence needs 126 batches; leave a 30 minute host/API margin.
    remaining = (datetime.combine(now_pt.date() + timedelta(days=1), datetime.min.time(), tzinfo=ZoneInfo('America/Los_Angeles')) - now_pt).total_seconds()
    if remaining < 125 * 61 + 1800:
        raise PermissionError('Insufficient time before next Pacific quota boundary')
    if manifest['pending_api_calls'] != 118 or manifest['pending_count'] != 252:
        raise PermissionError('Pending frame changed')


def live(receipt_path, run_name):
    manifest = verify_frozen()
    receipt = read(receipt_path)
    validate_clearance(receipt, manifest)
    if not os.getenv('GEMINI_API_KEY') or os.getenv('GOOGLE_API_KEY'):
        raise PermissionError('Credential configuration not isolated')
    if any(os.getenv(k) for k in ('REPORT_MODEL', 'REPORT_GEMINI_API_KEY', 'GOOGLE_GENAI_USE_VERTEXAI',
          'GOOGLE_GEMINI_BASE_URL', 'GOOGLE_VERTEX_BASE_URL', 'HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY',
          'http_proxy', 'https_proxy', 'all_proxy')):
        raise PermissionError('Unexpected endpoint/credential override')
    if not run_name or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-' for c in run_name):
        raise ValueError('Invalid continuation name')
    ledger = {x['source_case']: x for x in read(EXPORT / 'local_only/CASE_TRANSFER_LEDGER.json')}
    order = [{'case_id': x['case_id'], 'arm': x['arm']} for x in manifest['entries']]
    def load(item):
        routed = route(ledger[item['case_id']], item['arm'])
        exact = next(x for x in manifest['entries'] if (x['case_id'], x['arm']) == (item['case_id'], item['arm']))
        if item['arm'] in 'AB':
            request = AMENDMENT / 'requests' / (ledger[item['case_id']]['export_case'] + '_' + item['arm'] + '.json')
            if read(request) != routed['request'] or sha(request) != exact['request_sha256']:
                raise ValueError('Frozen request mismatch')
        return routed
    reservations = {(x['case_id'], x['arm']): x['planning_tokens'] for x in manifest['entries'] if x['arm'] in 'AB'}
    if sum(price(v, 4096) for v in reservations.values()) > receipt['budget_usd']:
        raise PermissionError('Full pending frame exceeds budget')
    def quota_day():
        return datetime.now(ZoneInfo('America/Los_Angeles')).date().isoformat()
    write(BASE / ('LAUNCH_RESERVED_' + receipt['authorization_id'] + '.json'),
          {'time': now(), 'receipt_sha256': sha(receipt_path), 'run_name': run_name,
           'pending_manifest_sha256': sha(PREP / 'PENDING_SLOTS.json')})
    return run_frame(order, BASE / run_name, load, send_gemini, reservations,
                     budget=receipt['budget_usd'], rpm=receipt['rpm_available'],
                     tpm=receipt['tpm_available'], rpd_remaining=receipt['rpd_remaining'],
                     quota_day=quota_day)


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--freeze', action='store_true')
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--clearance')
    parser.add_argument('--run-name')
    args = parser.parse_args()
    if args.freeze and not args.execute:
        print(json.dumps({'pending_manifest_sha256': freeze()}))
    elif args.execute and not args.freeze and args.clearance and args.run_name:
        print(json.dumps(live(args.clearance, args.run_name)))
    else:
        parser.error('Specify --freeze or a cleared --execute')
