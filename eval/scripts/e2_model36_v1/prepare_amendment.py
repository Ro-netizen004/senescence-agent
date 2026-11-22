"""Exclusive local amendment preparation. Never generates reports or sends data."""
import math
import os
from collections import Counter
from common import ROOT, OUT, read, write, sha, digest, now
from privacy_export import DEST as EXPORT, original_preservation
from integration import DEST, MODEL, CONFIG, verify_export, route


def main():
    os.umask(0o077)
    assert not (DEST / 'AMENDMENT_LOCK.json').exists()
    verify_export()
    before = original_preservation()
    (DEST / 'requests').mkdir(parents=True, exist_ok=False)
    records = read(EXPORT / 'local_only/CASE_TRANSFER_LEDGER.json')
    assert len(records) == 102
    routing, count_rows = [], []
    for rec in records:
        row = {'source_case': rec['source_case'], 'export_case': rec['export_case'],
               'canonical_sha256': rec['original_packet_sha256'],
               'sanitized_sha256': rec['sanitized_packet_sha256'],
               'gate_signature': rec['gate_signature'], 'arms': {}}
        for arm in 'ABCD':
            r = route(rec, arm)
            entry = {'packet_content_sha256': r['packet_content_sha256'],
                     'model_input': None, 'implementation': {'A': 'Gemini', 'B': 'Gemini',
                         'C': 'frozen reporters.template', 'D': 'frozen reporters.firewall + adapter_v1'}[arm]}
            if r['request'] is not None:
                path = DEST / 'requests' / (rec['export_case'] + '_' + arm + '.json')
                write(path, r['request'])
                entry.update(model_input=str(path.relative_to(DEST)), request_sha256=sha(path),
                             prior_request_sha256=rec['requests'][arm]['sha256'])
                text = r['request']['contents'] + r['request']['config']['system_instruction']
                count_rows.append({'file': str(path.relative_to(DEST)), 'characters': len(text),
                    'estimated_tokens': {str(n): math.ceil(len(text) / n) for n in (4, 3, 2)}})
            row['arms'][arm] = entry
        assert len({a['packet_content_sha256'] for a in row['arms'].values()}) == 1
        routing.append(row)
    order = read(OUT / 'E2_EXECUTION_ORDER.json')
    assert Counter(r['arm'] for r in order['order']) == dict.fromkeys('ABCD', 102)
    write(DEST / 'EXECUTION_CONFIG.json', CONFIG)
    write(DEST / 'EXECUTION_ORDER.json', order)
    write(DEST / 'ROUTING_LEDGER_LOCAL_ONLY.json', routing)
    scenarios = []
    for ratio in (4, 3, 2):
        n = sum(r['estimated_tokens'][str(ratio)] for r in count_rows)
        scenarios.append({'characters_per_token': ratio, 'input_tokens_estimated': n,
                          'output_cap_including_thinking': 204 * 4096,
                          'usd_at_current_standard_rates': (n * .75 + 204 * 4096 * 3.75) / 1e6,
                          'usd_at_announced_2027_rates': (n * 1.5 + 204 * 4096 * 7.5) / 1e6})
    write(DEST / 'BUDGET_AND_QUOTA.json', {
        'model': MODEL, 'max_calls': 204, 'calls_by_arm': {'A': 102, 'B': 102, 'C': 0, 'D': 0},
        'slots': 408, 'current_usd_per_million_input_output': [.75, 3.75],
        'price_valid_through': '2026-12-31', 'source': 'https://ai.google.dev/gemini-api/docs/pricing',
        'total_characters': sum(r['characters'] for r in count_rows), 'requests': count_rows,
        'scenarios': scenarios, 'exact_input_tokens': None,
        'estimate_limitations': 'Offline heuristic, not bounds; no provider token counting. Unknown framing, taxes, FX, synthetic tests and other usage excluded.',
        'usd5_assessment': 'LIKELY_SUFFICIENT_NOT_GUARANTEED under current standard prices',
        'project_RPM_TPM_RPD': 'NOT_VERIFIED', 'available_daily_headroom': 'NOT_VERIFIED',
        'quota_policy': 'Do not launch without current project-specific limits/headroom and a documented feasible pacing plan. At most 2 jobs is not a rate guarantee; no quota probing or silent retry.',
        'new_api_calls': 0})
    write(DEST / 'PRESERVATION_BEFORE.json', before)
    write(DEST / 'PREPARATION_STATUS.json', {'time': now(),
        'status': 'PREPARED_NOT_EXECUTION_AUTHORIZED', 'requested_model': MODEL,
        'actual_scored_backend': None, 'new_api_calls': 0, 'scored_reports': 0,
        'research_transfers': 0, 'real_case_reports_rendered': 0,
        'prior_synthetic_requested': 'gemini-3.5-flash', 'prior_synthetic_returned': MODEL,
        'original_status': 'E2_BLOCKED', 'billing_link': 'USER_ATTESTED_NOT_INDEPENDENTLY_VISIBLE',
        'institutional_data_authorization': 'NOT_VERIFIED', 'quota': 'NOT_VERIFIED',
        'final_execution_approval': False})
    print('Prepared 204 model-amended requests and 408 routes locally; no reports or API calls.')


if __name__ == '__main__':
    main()
