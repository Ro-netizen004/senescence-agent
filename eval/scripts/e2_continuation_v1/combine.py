"""Prespecified two-attempt E2 merger using unchanged original screen and metrics."""
import hashlib
import json
import random
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

from common import ROOT, OUT, E1, encode, now, read, sha, textfile, write
from continuation import ORIGINAL, ORIGINAL_ANALYSIS, PREP, verify_frozen
from integration import DEST as AMENDMENT
from privacy_export import DEST as EXPORT
from orchestrator import seal, verify_manifest
from scoring import score
from finalize import aggregate, verify_aggregation_independently
from finalize_amended import paired

BASE = ROOT / 'eval/results/v2/e2'
CONTINUATION = BASE / 'e2_gemini36_continuation_v1_20261025_01'
DEST = BASE / 'e2_gemini36_combined_v1_20261025_01'
E4 = BASE / 'e2_e4_blinded_preparation_v1_20261025_01'


def source_records():
    frozen = verify_frozen()
    verify_manifest(CONTINUATION)
    start = read(CONTINUATION / 'STARTED.json')
    requested = [(x['case_id'], x['arm']) for x in start['order']]
    expected = [(x['case_id'], x['arm']) for x in frozen['entries']]
    if requested != expected:
        raise ValueError('Continuation order differs from sealed pending order')
    pending = set(expected)
    originals = {}
    continued = {}
    for slot in ORIGINAL.iterdir():
        if not slot.is_dir():
            continue
        recfile = slot / 'RESPONSE.json'
        if recfile.exists():
            verify_manifest(slot)
            rec = read(recfile)
            key = rec['case_id'], rec['arm']
            if key in originals or key in pending:
                raise ValueError('Original attempted identity duplicated in pending set')
            originals[key] = rec
    for slot in CONTINUATION.iterdir():
        if not slot.is_dir():
            continue
        recfile = slot / 'RESPONSE.json'
        if recfile.exists():
            verify_manifest(slot)
            rec = read(recfile)
            key = rec['case_id'], rec['arm']
            if key in continued or key not in pending or key in originals:
                raise ValueError('Continuation attempted an ineligible/duplicate slot')
            continued[key] = rec
    if len(originals) != 156:
        raise ValueError('Original attempted count changed')
    return frozen, originals, continued


def combine_rows(frame, originals, continued, ledger):
    records = []
    for case in frame:
        keycase = case['case_id']
        packet = read(EXPORT / ledger[keycase]['packet_file'])
        for arm in 'ABCD':
            key = keycase, arm
            if key in originals:
                rec = dict(originals[key]); source = ORIGINAL; label = 'attempt1'
            elif key in continued:
                rec = dict(continued[key]); source = CONTINUATION; label = 'continuation1'
            else:
                slot = CONTINUATION / f'{keycase}_{arm}'
                rec = {'case_id': keycase, 'arm': arm,
                       'status': 'INCOMPLETE_RESERVED' if slot.exists() else 'NOT_EXECUTED',
                       'text': '', 'api_calls': int((slot/'API_ATTEMPT_RESERVED.json').exists()),
                       'retries': 0, 'estimated_usd': None}
                label = 'continuation1_pending'; source = None
            if source is not None:
                slot = source / f'{keycase}_{arm}'
                if read(slot / 'REPORTER_VISIBLE_PACKET.json') != packet:
                    raise ValueError('Reporter packet parity failed')
                if arm in 'AB':
                    expected = AMENDMENT / 'requests' / (ledger[keycase]['export_case'] + '_' + arm + '.json')
                    if read(slot / 'REQUEST.json') != read(expected):
                        raise ValueError('Gemini request changed')
                if (rec['case_id'], rec['arm']) != key or rec.get('requested_model') not in (
                        'gemini-3.6-flash' if arm in 'AB' else None,):
                    raise ValueError('Model/slot identity changed')
            rec['family'] = case['family']
            rec['source_attempt'] = label
            records.append(rec)
    if len(records) != 408 or len({(r['case_id'], r['arm']) for r in records}) != 408:
        raise ValueError('Combined frame is not unique 408-slot design')
    return records


def four_arm_complete(scores, frame):
    by = {(r['case_id'], r['arm']): r for r in scores}
    out = []
    for family in 'F1 F2 F3 F4'.split():
        cases = [x['case_id'] for x in frame if x['family'] == family]
        complete = [c for c in cases if all(by[c, a]['status'] == 'SUCCESS' for a in 'ABCD')]
        row = {'family': family, 'planned_contexts': len(cases),
               'complete_four_arm_contexts': len(complete),
               'incomplete_four_arm_contexts': len(cases) - len(complete), 'arms': {}}
        for arm in 'ABCD':
            chosen = [by[c, arm] for c in complete]
            events = sum(x['unsupported_screen_event'] is True for x in chosen)
            denominator = sum(x['opportunities'] for x in chosen)
            retained = sum(x['retained'] for x in chosen)
            row['arms'][arm] = {'provisional_events': events,
                                'event_rate_complete_four_arm': events / len(complete) if complete else None,
                                'retained': retained, 'opportunities': denominator,
                                'retention_complete_four_arm': retained / denominator if denominator else None}
        out.append(row)
    return out


def fixed_audit_sample(scores):
    flagged = []
    for x in scores:
        if x['arm'] == 'D' and x['status'] == 'SUCCESS' and any(
                f['category'] == 'artifact_origin_candidate' for f in x['screen_flags']):
            flagged.append(x['case_id'])
    flagged.sort(key=lambda c: (hashlib.sha256(c.encode()).hexdigest(), c))
    return {'selection': '12 smallest SHA256(case_id) among completed D artifact_origin_candidate flags',
            'eligible_flags': len(flagged), 'selected_case_ids': flagged[:12],
            'audit_rubric': 'CONTINUATION_PROTOCOL.md; single-reviewer exploratory audit; no rescoring'}


def e4_package(records, e4dir):
    e4dir.mkdir(exist_ok=False)
    sample = read(OUT / 'E2_E4_SAMPLE.json')['contexts']
    ledger = {x['source_case']: x for x in read(EXPORT / 'local_only/CASE_TRANSFER_LEDGER.json')}
    if len(sample) != 40 or len(set(sample)) != 40:
        raise ValueError('Frozen E4 sample changed')
    by = {(r['case_id'], r['arm']): r for r in records}
    rng = random.Random(20261025)
    public = []
    private = []
    index = 0
    for i, case in enumerate(sample):
        # Use the same privacy-minimized facts that all four E2 reporters saw.
        source = read(EXPORT / ledger[case]['packet_file'])
        source.pop('provenance', None)
        source['case_id'] = f'CONTEXT_{i+1:03d}'
        source['perturbation_identity'].pop('mapping_source', None)
        write(e4dir / f'CONTEXT_{i+1:03d}.json', source)
        arms = list('ABCD'); rng.shuffle(arms)
        for arm in arms:
            rec = by[case, arm]
            index += 1
            blinded = f'R{index:04d}'
            masked = re.sub(r'(?m)^\[System\] inference_state=.*(?:\n|$)', '', rec['text'])
            text = masked if rec['text'] else '[OUTPUT UNAVAILABLE: ' + rec['status'] + ']'
            textfile(e4dir / f'{blinded}.txt', text)
            public.append({'response_id': blinded, 'context_id': source['case_id'],
                           'status': rec['status']})
            private.append({'response_id': blinded, 'case_id': case, 'arm': arm,
                            'source_attempt': rec['source_attempt'],
                            'original_text_sha256': hashlib.sha256(rec['text'].encode()).hexdigest(),
                            'blinded_text_sha256': sha(e4dir / f'{blinded}.txt'),
                            'technical_footer_removed': masked != rec['text']})
    write(e4dir / 'INDEX.json', public)
    textfile(e4dir / 'ATOMIC_RUBRIC.md', (E1 / 'E1_INDEPENDENT_CLAIM_CRITERIA_V1.md').read_text())
    textfile(e4dir / 'README.md', '# E4 preparation only\n\nThe original frozen 40-context sample has 160 response slots. Cases and arms are blinded with the same fixed seed. Missing or failed outputs have explicit placeholders. The technical inference footer alone is masked; substantive refusals remain verbatim and can reveal architecture. No safety scores, gate state, evaluator answer keys or donor source identifiers are included. Independent human claim assessment has not started.\n')
    return private


def main():
    frozen, originals, continued = source_records()
    frame = [json.loads(x) for x in (OUT / 'E2_CASE_MANIFEST.jsonl').read_text().splitlines()]
    ledger = {x['source_case']: x for x in read(EXPORT / 'local_only/CASE_TRANSFER_LEDGER.json')}
    records = combine_rows(frame, originals, continued, ledger)
    opportunities = defaultdict(list)
    for x in read(OUT / 'E2_SUPPORTED_OPPORTUNITIES.json'):
        opportunities[x['case_id']].append(x)
    scores = []
    for rec in records:
        packet = read(EXPORT / ledger[rec['case_id']]['packet_file'])
        s = score(rec, packet, opportunities[rec['case_id']]); s['family'] = rec['family']
        scores.append(s)
    aggregates = [aggregate(scores, f, a) for f in 'F1 F2 F3 F4'.split() for a in 'ABCD']
    independent = verify_aggregation_independently(scores, aggregates)
    pairs = paired(scores, frame)
    four = four_arm_complete(scores, frame)
    by = {(s['case_id'], s['arm']): s for s in scores}
    assert all(row['planned_contexts'] == sum(x['family'] == row['family'] for x in frame) for row in four)
    assert all(row['complete_four_arm_contexts'] == sum(all(by[c['case_id'], a]['status'] == 'SUCCESS' for a in 'ABCD')
                                                 for c in frame if c['family'] == row['family']) for row in four)
    observed = [r for r in records if r['status'] == 'SUCCESS']
    missing = [{k: r.get(k) for k in ('case_id', 'family', 'arm', 'status', 'source_attempt',
                                      'api_error_code', 'error_type')}
               for r in records if r['status'] != 'SUCCESS']
    status = 'E2_EXECUTION_COMPLETE_E4_PENDING' if not missing else 'E2_COVERAGE_COMPLETE_WITH_FAILURES_E4_PENDING' if len(originals)+len(continued)==408 else 'E2_PARTIAL'
    e4_private = e4_package(records, E4)
    e4_manifest_hash = seal(E4)
    DEST.mkdir(exist_ok=False)
    textfile(DEST / 'RESPONSES_WITH_ATTEMPTS.jsonl', ''.join(encode(r)+'\n' for r in records))
    textfile(DEST / 'PROVISIONAL_SCORES.jsonl', ''.join(encode(s)+'\n' for s in scores))
    write(DEST / 'FAMILY_METRICS.json', {'classification': status,
          'interpretation': 'FROZEN_PROVISIONAL_MACHINE_SCREEN_E4_PENDING',
          'families': aggregates, 'registered_pairs': pairs,
          'four_arm_complete_cases': four})
    write(DEST / 'INDEPENDENT_ARITHMETIC_CHECK.json', {'aggregation': independent,
          'four_arm_counts': 'PASS', 'source_partition': 'PASS', 'request_packet_parity': 'PASS'})
    write(DEST / 'FAILURES_AND_MISSINGNESS.json', missing)
    write(DEST / 'ARM_D_ARTIFACT_AUDIT_SAMPLE.json', fixed_audit_sample(scores))
    write(DEST / 'E4_PRIVATE_BLINDING_KEY.json', e4_private)
    write(DEST / 'E4_PUBLIC_PACKAGE_REFERENCE.json', {'directory': str(E4.relative_to(ROOT)),
          'sha256_manifest': e4_manifest_hash, 'sample_contexts': 40, 'response_slots': 160,
          'E4_scoring': 'NOT_STARTED'})
    all_attempted = list(originals.values()) + list(continued.values())
    gen = {'time': now(), 'classification': status, 'planned_contexts': 102,
           'planned_slots': 408, 'attempt1_status': read(ORIGINAL / 'SUMMARY.json')['status'],
           'continuation_status': read(CONTINUATION / 'SUMMARY.json')['status'],
           'attempt1_counts': dict(Counter(x['status'] for x in originals.values())),
           'continuation_counts': dict(Counter(x['status'] for x in continued.values())),
           'combined_counts': dict(Counter(x['status'] for x in records)),
           'all_slots_attempted': len(originals)+len(continued),
           'api_calls_attempt1': sum(x['api_calls'] for x in originals.values()),
           'api_calls_continuation': sum(x['api_calls'] for x in continued.values()),
           'api_calls_combined': sum(x['api_calls'] for x in all_attempted),
           'retries': sum(x['retries'] for x in all_attempted), 'new_scientific_fits': 0,
           'requested_backend': 'gemini-3.6-flash',
           'actual_backends': sorted({x.get('actual_backend') for x in all_attempted if x.get('actual_backend')}),
           'known_usage_estimated_usd': sum(x.get('estimated_usd') or 0 for x in all_attempted),
           'unknown_cost_api_attempts': sum(x['api_calls'] and x.get('estimated_usd') is None for x in all_attempted),
           'invoice_usd': None, 'original_manifest_sha256': sha(ORIGINAL / 'SHA256_MANIFEST.json'),
           'original_analysis_manifest_sha256': sha(ORIGINAL_ANALYSIS / 'SHA256_MANIFEST.json'),
           'continuation_manifest_sha256': sha(CONTINUATION / 'SHA256_MANIFEST.json'),
           'continuation_protocol_manifest_sha256': sha(PREP / 'SHA256_MANIFEST.json'),
           'E4_package_manifest_sha256': e4_manifest_hash, 'E4': 'PENDING_NOT_STARTED'}
    write(DEST / 'GENERATION_AND_PROVENANCE.json', gen)
    lines = ['# E2 controlled continuation: combined report',
      '\nClassification: **'+status+'**. E4: **PENDING_NOT_STARTED**.',
      '\nThe first attempt remains `E2_PARTIAL`; continuation includes exactly the sealed 252 never-dispatched slots. Provisional first-attempt results had already been observed when this continuation was registered. No failed/truncated slot was retried.',
      f"\nAttempt 1: {gen['attempt1_counts']}. Continuation: {gen['continuation_counts']}. Combined: {gen['combined_counts']}. Gemini attempts {gen['api_calls_attempt1']} + {gen['api_calls_continuation']} = {gen['api_calls_combined']}; retries {gen['retries']}; new fits 0.",
      '\n## Frozen family metrics',
      '\n|Family|Arm|Successful/planned|Screen flags/successful|Flag lower/planned|Retained/planned opportunities|Retained/successful opportunities|Refused|Partial|',
      '|---|---|---:|---:|---:|---:|---:|---:|---:|']
    for a in aggregates:
        lines.append(f"|{a['family']}|{a['arm']}|{a['completed']}/{a['planned']}|{a['provisional_screen_events']}/{a['completed']}|{a['screen_failure_bound_low']:.3f}|{a['retained_provisional']}/{a['conditional_numerical_opportunities']}|{a['retention_completed']}|{a['refused']}|{a['partial']}|")
    lines += ['\nF1=TMS constructed null; F2=OneK1K external null; F3=OneK1K engineered positive; F4=CRISPRi real target. Zero opportunities means retention undefined. The complete failure bounds and original D-B/D-C contrasts are in FAMILY_METRICS.json.',
      '\n## Four-arm complete-case comparison',
      '\n|Family|All four successful/planned|A flags|B flags|C flags|D flags|',
      '|---|---:|---:|---:|---:|---:|']
    for row in four:
        lines.append('|'+row['family']+'|'+str(row['complete_four_arm_contexts'])+'/'+str(row['planned_contexts'])+'|'+
                     '|'.join(str(row['arms'][a]['provisional_events']) for a in 'ABCD')+'|')
    lines += ['\nFour-arm rates use only jointly successful contexts. Planned-denominator bounds and intention-to-report retention count every registered context; these answer different questions and are not silently substituted.',
      '\n## Integrity and interpretation',
      '\nAll 408 original keys are represented once, with source-attempt labels. Frozen source/output manifests, packet parity, exact Gemini request objects, unchanged scoring and independent aggregate arithmetic verify. The first-run timeout and truncation artifacts remain untouched. A text-screen flag is only a candidate for E4 review; an unflagged output is not certified safe. No new biological analysis, inferential independence assumption or E4 scoring was performed.',
      f"\nKnown token-cost estimate ${gen['known_usage_estimated_usd']:.6f}; unknown-cost API attempts {gen['unknown_cost_api_attempts']}; invoice unavailable. Both run summaries preserve any quota/API/budget stops. The blinded E4 40-context/160-slot package is sealed separately; the local arm key remains in this analysis directory.",
      '\nThe Arm D artifact-origin audit sample and rubric were fixed before continuation scoring. Its separately labeled exploratory assessment must not alter these metrics or be described as validated ground truth. This E2 interface is the adapted reporting interface, not a retrospective validation of original E1.']
    textfile(DEST / 'COMBINED_REPORT.md', '\n'.join(lines)+'\n')
    print(json.dumps({'classification': status, 'combined_manifest_sha256': seal(DEST),
                      'E4_manifest_sha256': e4_manifest_hash}))


if __name__ == '__main__':
    main()
