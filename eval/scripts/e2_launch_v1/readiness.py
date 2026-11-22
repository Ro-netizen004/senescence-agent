"""Offline validation/artifact generation. Does not invoke live()."""
import os
import subprocess
import sys
from pathlib import Path
from collections import Counter
from common import ROOT, OUT, read, write, textfile, sha, now
from integration import DEST as AMENDMENT, route
from privacy_export import DEST as EXPORT
from orchestrator import REVIEW, verify_amendment, planning_tokens, price, run_frame, seal


def field_paths(value, prefix=''):
    if isinstance(value, dict) and value:
        result = set()
        for key, item in value.items():
            key = '<case-local-pair-alias>' if key.startswith('pair_') else key
            result |= field_paths(item, prefix + '/' + key)
        return result
    if isinstance(value, list) and value:
        return set().union(*(field_paths(item, prefix + '/[]') for item in value))
    return {prefix}


def main():
    os.umask(0o077)
    REVIEW.mkdir(exist_ok=True)
    if sys.argv[1:] == ['--seal']:
        return freeze()
    write(REVIEW / 'PRESERVATION_BEFORE.json', verify_amendment())
    logdir = REVIEW / 'validation_01'
    logdir.mkdir(exist_ok=False)
    commands = [
        [sys.executable, '-m', 'unittest', 'discover', '-s', 'eval/scripts/e2_launch_v1', '-p', 'test_orchestrator.py', '-v'],
        *[[sys.executable, '-m', 'unittest', 'discover', '-s', 'eval/scripts/' + folder, '-p', pattern, '-v']
          for folder, pattern in [('e2_model36_v1', 'test_model36.py'), ('e2_privacy_v1', 'test_privacy_export.py'), ('e2', 'test_e2.py')]],
        [sys.executable, '-m', 'unittest', '-v', *['backend/tests/' + f for f in [
            'test_output_firewall.py', 'test_inference_state.py', 'test_admissibility_confounding.py',
            'test_admissibility_replicates.py', 'test_governance_method_parity.py', 'test_governance_guard.py']]],
        [sys.executable, '-m', 'pip', 'check']]
    checks = []
    for i, command in enumerate(commands, 1):
        r = subprocess.run(command, cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        path = logdir / f'CHECK_{i}.txt'
        textfile(path, 'COMMAND: ' + ' '.join(command) + '\n' + r.stdout)
        checks.append({'file': str(path.relative_to(ROOT)), 'sha256': sha(path), 'exit_code': r.returncode})
        print(f'Check {i}: exit {r.returncode}', flush=True)
        if r.returncode:
            raise SystemExit('Failed local validation; log preserved; no lock')
    packages = subprocess.run([sys.executable, '-m', 'pip', 'freeze', '--all'], text=True, capture_output=True, check=True).stdout
    assert sorted(packages.splitlines()) == sorted((OUT / 'ENVIRONMENT_FREEZE.txt').read_text().splitlines())
    assert sys.version.split()[0] == '3.11.9' and Path(sys.executable).parent.parent.name == '.venv-task2'
    textfile(REVIEW / 'ENVIRONMENT_FREEZE.txt', packages)
    ledger = read(EXPORT / 'local_only/CASE_TRANSFER_LEDGER.json')
    costs = []; fields = set(); routes = []
    for record in ledger:
        for arm in 'ABCD':
            routed = route(record, arm)
            routes.append({'source_case': record['source_case'], 'arm': arm,
                           'packet_sha256': routed['packet_sha256'], 'gate_signature': routed['gate_signature']})
            if arm in 'AB':
                req = routed['request']; fields |= field_paths(routed['packet'])
                path = AMENDMENT / 'requests' / (record['export_case'] + '_' + arm + '.json')
                assert req == read(path)
                tokens = planning_tokens(req)
                costs.append({'case_id': record['source_case'], 'arm': arm, 'request_sha256': sha(path),
                              'planning_input_tokens': tokens, 'planning_full_cap_usd': price(tokens, 4096)})
    assert Counter(r['arm'] for r in routes) == dict.fromkeys('ABCD', 102)
    assert len(costs) == 204
    reservations = {(r['case_id'], r['arm']): r['planning_input_tokens'] for r in costs}
    order = read(AMENDMENT / 'EXECUTION_ORDER.json')['order']
    largest_batch = max(sum(reservations.get((i['case_id'], i['arm']), 0) for i in order[j:j+2]) for j in range(0,408,2))
    write(REVIEW / 'ROUTING_VERIFICATION_LOCAL_ONLY.json', routes)
    write(REVIEW / 'OUTGOING_FIELD_PATHS.json', {'scope': 'Fields inside contents evidence JSON, not values',
        'envelope_fields': ['model', 'contents', 'config.system_instruction', 'config.temperature', 'config.max_output_tokens'],
        'evidence_leaf_paths': sorted(fields), 'new_fields_added': 0,
        'authoritative_request_root': str((AMENDMENT / 'requests').relative_to(ROOT)),
        'privacy_lock_sha256': sha(EXPORT / 'EXPORT_SPEC_LOCK.json')})
    write(REVIEW / 'QUOTA_BUDGET_PLAN.json', {'time': now(), 'project_id': 'gen-lang-client-0924718643',
        'model': 'gemini-3.6-flash', 'project_specific_rpm': None, 'project_specific_tpm': None,
        'project_specific_rpd': None, 'quota_verified': False, 'calls_by_arm': {'A':102,'B':102,'C':0,'D':0},
        'local_slots': {'C':102,'D':102}, 'max_calls':204, 'output_tokens_cap_total':204*4096,
        'output_cap_cost_usd':price(0,204*4096), 'usd5_input_token_allowance_before_extras':(5-price(0,204*4096))/.75*1e6,
        'planning_proxy':'UTF-8 system+user bytes + 1024 tokens/request for framing; conservative scenario, NOT certified upper bound',
        'planning_input_total':sum(r['planning_input_tokens'] for r in costs),
        'planning_full_cap_usd':sum(r['planning_full_cap_usd'] for r in costs),
        'prior_char_based_estimate_usd':[3.44,3.75], 'balance_snapshot_usd':5,
        'live_balance_verified':False, 'sufficiency':'LIKELY_NOT_GUARANTEED; actual usage/invoice may differ',
        'price_per_million_input_output':[.75,3.75], 'price_valid_through':'2026-12-31',
        'conditional_launch':{'batch_size':2,'batch_start_spacing_seconds':61,'max_concurrency':2,
            'required_available_rpm':2,'required_available_rpd':204,
            'largest_planning_batch_input_tokens':largest_batch,
            'minimum_available_tpm_with_20pct_margin':__import__('math').ceil(largest_batch/.8),
            'minimum_408slot_dispatch_span_seconds':203*61,
            'conditions':['Dedicated quota headroom/no other project traffic; verify before launch',
                          'Stop at quota reset boundary; no automatic resume',
                          'RPM/TPM/RPD/spend/credit evidence and approval required; no provider probes',
                          'If quotas do not fit, remain blocked; any pacing revision prospectively recorded']},
        'budget_failure_handling':'Preserve attempted failure, stop unstarted slots if planning budget exhausted; no shorter outputs, fallback, replacements or case selection',
        'items':costs})
    # Preserve representative mock execution artifacts, separate from scientific frame.
    from test_orchestrator import LaunchTests, dummy_response, FakeClock
    helper = LaunchTests()
    synthetic = helper.order()
    reserve = {(i['case_id'],i['arm']):planning_tokens(helper.loader(i)['request']) for i in synthetic if i['arm'] in 'AB'}
    mock_records = []
    for name in ('success', 'api_failure', 'budget_block'):
        clock = FakeClock(); dest = REVIEW / ('SYNTHETIC_ONLY_' + name)
        class DummyFailure(Exception): code = 503
        def send(req):
            if name == 'api_failure': raise DummyFailure()
            return dummy_response()
        try:
            run_frame(synthetic, dest, helper.loader, send, reserve, budget=.001 if name=='budget_block' else 5,
                rpm=2,tpm=100000,rpd_remaining=204,sleep=clock.sleep,clock=clock.now,classification='SYNTHETIC_ONLY_NOT_SCORED')
        except PermissionError:
            assert name == 'budget_block'
        mock_records.append({'directory':dest.name,'manifest_sha256':sha(dest/'SHA256_MANIFEST.json')})
    write(REVIEW / 'PRESERVATION_AFTER.json', verify_amendment())
    write(REVIEW / 'VALIDATION_SUMMARY.json', {'time':now(),'status':'PASS_OFFLINE_ONLY_NO_GO',
        'checks':checks,'tests':102,'new_orchestrator_tests':19,'prior_tests':83,
        'synthetic_artifacts':mock_records,'environment_matches':True,
        'real_cases_rendered':0,'new_api_calls':0,'scored_calls':0,'research_transfers':0,
        'scientific_protocol_changed':False,'all_408_routes_verified':True})


def freeze():
    verify_amendment()
    summary = read(REVIEW/'VALIDATION_SUMMARY.json')
    for r in summary['checks']: assert r['exit_code']==0 and sha(ROOT/r['file'])==r['sha256']
    final = read(REVIEW/'FINAL_VALIDATION_V2.json')
    for r in final['checks']: assert r['exit_code']==0 and sha(REVIEW/r['file'])==r['sha256']
    files = list(REVIEW.rglob('*')) + list((ROOT/'eval/scripts/e2_launch_v1').glob('*.py'))
    entries = {str(p.relative_to(ROOT)):sha(p) for p in sorted(files) if p.is_file() and '__pycache__' not in p.parts}
    write(REVIEW/'READINESS_LOCK.json',{'time':now(),'status':'FROZEN_OFFLINE_READINESS_NO_GO',
        'files':entries,'execution_authorized':False,'new_api_calls':0,
        'amendment_lock_sha256':sha(AMENDMENT/'AMENDMENT_LOCK.json')})
    print('readiness_lock_sha256='+sha(REVIEW/'READINESS_LOCK.json'))


if __name__ == '__main__': main()
