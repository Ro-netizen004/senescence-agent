"""E2 launch implementation; tests inject synthetic-only loaders/transports.

No implicit launch, resumption, credential-file reads, or retries. Live access
requires independently reviewed clearance and --execute from a separate approval.
"""
import concurrent.futures
import hashlib
import json
import math
import os
from pathlib import Path
import time
from datetime import datetime, timezone

from common import ROOT, OUT, read, sha, digest, write, now
from integration import (DEST as AMENDMENT, MODEL, verify_export, route,
                         sdk_arguments, response_status, local_report, require_clearance)
from privacy_export import DEST as EXPORT, original_preservation

PROTOCOL_HASH = '85138909eebd21b1abfa7995a1474bcc634404bad1dd96e310f450e0ffaa60be'
LOCK_HASH = 'd4092071e8a72c74b3ca6af9882e896c37c65b60ce69a6ca88de2b3afb89027a'
REVIEW = ROOT / 'eval/results/v2/e2/e2_final_readiness_v1_20261024_01'
RATES = {'input': .75, 'output': 3.75}


def verify_amendment():
    if sha(AMENDMENT / 'AMENDMENT_LOCK.json') != LOCK_HASH or sha(AMENDMENT / 'E2_MODEL_AMENDMENT_V1.md') != PROTOCOL_HASH:
        raise ValueError('Frozen amendment identity mismatch')
    for p, h in read(AMENDMENT / 'AMENDMENT_LOCK.json')['files'].items():
        if sha(ROOT / p) != h:
            raise ValueError('Frozen amendment file mismatch')
    verify_export()
    return original_preservation()


def planning_tokens(request):
    # Conservative planning proxy, NOT a certified tokenizer upper bound.
    return len((request['contents'] + request['config']['system_instruction']).encode('utf-8')) + 1024


def price(input_tokens, output_tokens):
    return (input_tokens * RATES['input'] + output_tokens * RATES['output']) / 1_000_000


def response_record(response):
    # Capture JSON before derived parsing; no credentials/headers/exception bodies.
    return response.model_dump(mode='json')


def usage_cost(raw):
    u = raw.get('usage_metadata') or {}
    fields = [u.get(k) for k in ('prompt_token_count', 'candidates_token_count', 'thoughts_token_count')]
    if any(not isinstance(v, int) or isinstance(v, bool) or v < 0 for v in fields):
        return None
    return price(fields[0], fields[1] + fields[2])


def seal(directory):
    """Exclusive manifest and read-only files; hash-verifiable, not OS-root WORM."""
    directory = Path(directory)
    entries = {str(p.relative_to(directory)): sha(p) for p in sorted(directory.rglob('*')) if p.is_file()}
    write(directory / 'SHA256_MANIFEST.json', {'files': entries, 'sealed_utc': now()})
    for p in directory.rglob('*'):
        if p.is_file():
            p.chmod(0o400)
    return sha(directory / 'SHA256_MANIFEST.json')


def verify_manifest(directory):
    m = read(Path(directory) / 'SHA256_MANIFEST.json')
    for p, h in m['files'].items():
        if sha(Path(directory) / p) != h:
            raise ValueError('Sealed artifact changed')
    actual = {str(p.relative_to(directory)) for p in Path(directory).rglob('*') if p.is_file()}
    if actual != set(m['files']) | {'SHA256_MANIFEST.json'}:
        raise ValueError('Unexpected sealed file set')


def run_slot(item, root, load, send, render=local_report):
    case, arm = item['case_id'], item['arm']
    if arm not in ('A', 'B', 'C', 'D') or not case or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-' for c in case):
        raise ValueError('Invalid slot identity')
    path = Path(root) / f'{case}_{arm}'
    path.mkdir(exist_ok=False)
    write(path / 'STARTED.json', {'time': now(), **item})
    rec = {**item, 'status': 'EXECUTION_FAILURE', 'api_calls': 0, 'retries': 0,
           'requested_model': MODEL if arm in 'AB' else None, 'actual_backend': None,
           'text': '', 'estimated_usd': 0.0 if arm in 'CD' else None, 'time_start': now()}
    start = time.monotonic()
    try:
        r = load(item)
        write(path / 'REPORTER_VISIBLE_PACKET.json', r['packet'])
        write(path / 'LOCAL_PROVENANCE.json', {k: v for k, v in r.items() if k not in ('packet', 'request', 'private')})
        if arm in 'AB':
            request = r['request']
            sdk_arguments(request)  # Fail before attempting network on bad input.
            write(path / 'REQUEST.json', request)
            rec['request_sha256'] = sha(path / 'REQUEST.json')
            rec['planning_input_tokens'] = planning_tokens(request)
            rec['planning_reservation_usd'] = price(rec['planning_input_tokens'], 4096)
            rec['api_calls'] = 1
            write(path / 'API_ATTEMPT_RESERVED.json', {'time': now(), 'attempt': 1,
                  'request_sha256': rec['request_sha256']})
            response = send(request)  # Exactly once; only exact request body.
            raw = response_record(response)
            write(path / 'PROVIDER_RESPONSE.json', raw)
            rec.update(actual_backend=response.model_version, text=response.text or '',
                       status=response_status(response), usage=raw.get('usage_metadata'),
                       estimated_usd=usage_cost(raw))
        else:
            write(path / 'REQUEST.json', {'model_input': None, 'implementation': 'frozen_' + arm,
                'packet_content_sha256': digest(r['packet'])})
            text, trace = render(arm, r['packet'], r['private'])
            if trace is not None:
                write(path / 'GOVERNANCE_TRACE.json', trace)
            rec.update(text=text, status='SUCCESS')
    except Exception as error:
        rec['status'] = 'API_FAILURE' if rec['api_calls'] else 'EXECUTION_FAILURE'
        rec['error_type'] = type(error).__name__
        code = getattr(error, 'code', None)
        rec['api_error_code'] = code if isinstance(code, int) else None
    finally:
        rec.update(time_end=now(), seconds=time.monotonic() - start)
        write(path / 'RESPONSE.json', rec)
        seal(path)
    return rec


def run_frame(order, root, load, send, reservations, *, budget, rpm, tpm,
              rpd_remaining, sleep=time.sleep, clock=time.monotonic, render=local_report,
              classification='REGISTERED_E2', quota_day=None):
    """Fixed batches of two; 61s between starts; never retry or select replacements.

    quota_day is an optional callback reporting the project reset day. A reset
    stops this run for renewed headroom verification rather than auto-resuming.
    """
    if len(order) > 408 or len({(i['case_id'], i['arm']) for i in order}) != len(order):
        raise ValueError('Invalid or duplicate frame')
    root = Path(root)
    root.mkdir(exist_ok=False, parents=False)
    try:
        if any(not isinstance(v, (int,float)) or isinstance(v,bool) or not math.isfinite(v) or v <= 0
               for v in (budget, rpm, tpm, rpd_remaining)):
            raise PermissionError('Invalid budget/quota values')
        n_api = sum(i['arm'] in 'AB' for i in order)
        if n_api > 204 or rpd_remaining < n_api or rpm < 2:
            raise PermissionError('Request quota preflight blocked')
        for index in range(0, len(order), 2):
            if sum(reservations.get((i['case_id'], i['arm']), 0) for i in order[index:index+2]) > .8 * tpm:
                raise PermissionError('Token quota preflight blocked')
        planned = sum(price(reservations[(i['case_id'], i['arm'])], 4096) for i in order if i['arm'] in 'AB')
        if planned > budget:
            raise PermissionError('Full-frame budget planning blocked; no partial selection')
    except Exception as error:
        write(root / 'PREFLIGHT_BLOCKED.json', {'time': now(), 'classification': classification,
              'status': 'PREFLIGHT_BLOCKED', 'reason': str(error), 'api_calls': 0})
        seal(root)
        raise
    write(root / 'STARTED.json', {'time': now(), 'classification': classification,
          'protocol_sha256': PROTOCOL_HASH, 'amendment_lock_sha256': LOCK_HASH,
          'order': order, 'max_calls': 204, 'budget_usd': budget,
          'planning_full_cap_usd': planned, 'budget_is_not_invoice_guarantee': True})
    completed = []; halt = None; consecutive = 0; last_batch = None; accounted = 0.0
    day = quota_day() if quota_day else None
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            for index in range(0, len(order), 2):
                if quota_day and quota_day() != day:
                    halt = 'QUOTA_WINDOW_CHANGED'; break
                batch = order[index:index+2]
                needed = sum(price(reservations[(i['case_id'], i['arm'])], 4096) for i in batch if i['arm'] in 'AB')
                if accounted + needed > budget:
                    halt = 'BUDGET_PLANNING_STOP'; break
                if last_batch is not None:
                    delay = max(0, 61 - (clock() - last_batch))
                    if delay:
                        sleep(delay)
                if quota_day and quota_day() != day:
                    halt = 'QUOTA_WINDOW_CHANGED'; break
                last_batch = clock()
                futures = [pool.submit(run_slot, i, root, load, send, render) for i in batch]
                records = [f.result() for f in futures]
                for r in records:  # Seeded dispatch order, not completion-time selection.
                    completed.append(r)
                    if r['api_calls']:
                        if r['estimated_usd'] is None:
                            accounted += r.get('planning_reservation_usd', price(reservations[(r['case_id'], r['arm'])], 4096))
                        else:
                            accounted += r['estimated_usd']
                        consecutive = consecutive + 1 if r['status'] in ('API_FAILURE', 'EMPTY_RESPONSE') else 0
                    if r.get('api_error_code') in (401, 403):
                        halt = 'AUTHENTICATION_OR_PERMISSION_FAILURE'
                    if consecutive >= 3:
                        halt = halt or 'THREE_CONSECUTIVE_API_FAILURES'
                    if r['status'] == 'MODEL_MISMATCH':
                        halt = 'MODEL_MISMATCH'
                    if r['status'] == 'EXECUTION_FAILURE':
                        halt = halt or 'LOCAL_INFRASTRUCTURE_FAILURE'
                if accounted > budget:
                    halt = 'BUDGET_PLANNING_STOP'
                if halt:
                    break
    except BaseException as error:
        # Exception message/traceback may contain request or secrets: type only.
        halt = 'ORCHESTRATOR_INTERRUPTED_' + type(error).__name__
    finally:
        # Recover finished slots if interruption happened between future collection
        # and aggregation; started-without-response remains explicitly incomplete.
        preserved = []
        for item in order:
            p = root / f"{item['case_id']}_{item['arm']}" / 'RESPONSE.json'
            if p.is_file():
                preserved.append(read(p))
        done = {(r['case_id'], r['arm']) for r in preserved}
        missing = [{**i, 'status': 'INCOMPLETE_RESERVED' if (root / f"{i['case_id']}_{i['arm']}").exists() else 'NOT_DISPATCHED'}
                   for i in order if (i['case_id'], i['arm']) not in done]
        known = sum(r['estimated_usd'] for r in preserved if r.get('estimated_usd') is not None)
        accounted_final = sum(r['estimated_usd'] if r.get('estimated_usd') is not None else
                              r.get('planning_reservation_usd', 0) for r in preserved)
        summary = {'classification': classification, 'time': now(), 'reason': halt or 'FRAME_COMPLETE',
                   'planned_slots': len(order), 'completed_slots': len(preserved), 'incomplete': missing,
                   'api_attempts': sum(r['api_calls'] for r in preserved), 'retries': 0,
                   'reserved_attempts_without_response': sum((root / f"{i['case_id']}_{i['arm']}" / 'API_ATTEMPT_RESERVED.json').exists() for i in missing),
                   'known_usage_estimated_usd': known,
                   'unknown_cost_attempts': sum(r['api_calls'] and r.get('estimated_usd') is None for r in preserved),
                   'invoice_cost': None, 'budget_planning_accounted_usd': accounted_final,
                   'status': 'E2_EXECUTION_COMPLETE_E4_PENDING' if not missing and all(r['status'] == 'SUCCESS' for r in preserved) else 'E2_PARTIAL'}
        if classification != 'REGISTERED_E2':
            summary['status'] = 'SYNTHETIC_TEST_ONLY'
        write(root / 'SUMMARY.json', summary)
        seal(root)
    return summary


def validate_clearance(receipt):
    require_clearance(receipt, PROTOCOL_HASH)
    if receipt.get('amendment_lock_sha256') != LOCK_HASH:
        raise PermissionError('Wrong amendment receipt')
    if receipt.get('project_id') != 'gen-lang-client-0924718643':
        raise PermissionError('Wrong project')
    if receipt.get('model') != MODEL or receipt.get('budget_risk_acknowledged') is not True:
        raise PermissionError('Model/budget clearance missing')
    identifier = receipt.get('authorization_id', '')
    if not identifier or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-' for c in identifier):
        raise PermissionError('Invalid authorization identifier')
    # Human evidence files are local-only; paths must be repository-relative.
    for key in ('billing_evidence', 'quota_evidence', 'data_permission', 'final_user_approval'):
        e = receipt.get(key, {})
        path = (ROOT / e.get('path', '')).resolve()
        if not path.is_relative_to(ROOT) or not path.is_file() or sha(path) != e.get('sha256'):
            raise PermissionError('Missing reviewed evidence')
    if datetime.now(timezone.utc) >= datetime.fromisoformat(receipt['expires_utc']):
        raise PermissionError('Expired clearance')
    if datetime.now(timezone.utc).date().isoformat() > '2026-12-31':
        raise PermissionError('Price period expired; new budget review required')


def send_gemini(request):
    """Transport used only after live clearance; tests mock the SDK constructor."""
    from google import genai
    from google.genai import types
    client = genai.Client(api_key=os.getenv('GEMINI_API_KEY'), http_options=types.HttpOptions(
        timeout=120000, retry_options=types.HttpRetryOptions(attempts=1)))
    try:
        return client.models.generate_content(**sdk_arguments(request))
    finally:
        client.close()


def live(receipt_path, run_name):
    """Never invoked by readiness checks. No credentials persisted in receipts."""
    receipt = read(receipt_path)
    validate_clearance(receipt)  # Before credential access, any rendering or API client.
    verify_amendment()
    execution_lock = read(REVIEW / 'READINESS_LOCK.json')
    for p, h in execution_lock['files'].items():
        if sha(ROOT / p) != h:
            raise PermissionError('Launch implementation changed')
    if receipt.get('readiness_lock_sha256') != sha(REVIEW / 'READINESS_LOCK.json'):
        raise PermissionError('Launch implementation not approved')
    if not run_name or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-' for c in run_name):
        raise ValueError('Invalid run name')
    if not os.getenv('GEMINI_API_KEY') or os.getenv('GOOGLE_API_KEY'):
        raise PermissionError('Credential configuration not isolated')
    if any(os.getenv(k) for k in ('REPORT_MODEL', 'REPORT_GEMINI_API_KEY', 'GOOGLE_GENAI_USE_VERTEXAI',
          'GOOGLE_GEMINI_BASE_URL', 'GOOGLE_VERTEX_BASE_URL', 'HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY',
          'http_proxy', 'https_proxy', 'all_proxy')):
        raise PermissionError('Unexpected endpoint/credential overrides')
    records = {r['source_case']: r for r in read(EXPORT / 'local_only/CASE_TRANSFER_LEDGER.json')}
    order = read(AMENDMENT / 'EXECUTION_ORDER.json')['order']
    if len(order) != 408 or any(sum(i['arm'] == a for i in order) != 102 for a in 'ABCD'):
        raise ValueError('Frozen frame mismatch')
    def load(item):
        r = route(records[item['case_id']], item['arm'])
        if item['arm'] in 'AB':
            exact = read(AMENDMENT / 'requests' / (records[item['case_id']]['export_case'] + '_' + item['arm'] + '.json'))
            if exact != r['request']:
                raise ValueError('Frozen amended request mismatch')
        return r
    reservations = {(i['case_id'], i['arm']): planning_tokens(load(i)['request']) for i in order if i['arm'] in 'AB'}
    from zoneinfo import ZoneInfo
    def quota_day():
        return datetime.now(ZoneInfo('America/Los_Angeles')).date().isoformat()
    # Only one launch per separately authorized receipt; exclusive reservation.
    parent = ROOT / 'eval/results/v2/e2'
    write(parent / ('LAUNCH_RESERVED_' + receipt['authorization_id'] + '.json'),
          {'time': now(), 'receipt_sha256': sha(receipt_path), 'run_name': run_name})
    return run_frame(order, parent / run_name, load, send_gemini, reservations,
        budget=receipt['budget_usd'], rpm=receipt['rpm_available'], tpm=receipt['tpm_available'],
        rpd_remaining=receipt['rpd_remaining'], quota_day=quota_day)


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--clearance')
    parser.add_argument('--run-name')
    args = parser.parse_args()
    if not args.execute or not args.clearance or not args.run_name:
        parser.error('No default execution; separate verified authorization required')
    print(json.dumps(live(args.clearance, args.run_name)))
