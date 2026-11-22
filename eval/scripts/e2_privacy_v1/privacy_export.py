"""Local-only, fail-closed E2 export preparation. No SDK/client/network imports.

Run with PYTHONPATH=eval/scripts/e2:backend. Original E2 is never written.
The output is an approval candidate, NOT permission to transmit it.
"""
import copy
import os
import re
import secrets
from pathlib import Path

from common import ROOT, OUT, MODEL, read, sha, digest, encode, write, now, preservation, verify_lock
from reporters import REQUEST, PROMPTS, MODEL_CONFIG

DEST = ROOT / 'eval/results/v2/e2/e2_privacy_export_v1_20261024_01'
VERSION = 'e2_privacy_export_v1'
TOP = {'case_id', 'dataset', 'cell_type', 'biological_condition', 'perturbation_identity',
       'design', 'statistics', 'native_stability_facts', 'plausibility_facts', 'count_integrity',
       'inference_eligibility_evidence', 'paired_donor_sensitivity', 'numerical_warnings',
       'warning_scope', 'limitations', 'provenance', 'observed_significant_gene_ids'}
DESIGN = {'formula', 'independent_unit', 'n_samples', 'donors_by_group', 'paired',
          'independent_donor_pairs', 'residual_df', 'eligible_donors', 'allocation_id', 'donor_ids'}
STATS = {'contrast', 'positive_log2FC_means', 'n_significant_fdr_0_05', 'rows',
         'n_preserved_rows', 'selection_rule', 'missingness', 'on_target_family_A'}
ROW = {'gene', 'symbol', 'baseMean', 'log2FoldChange', 'lfcSE', 'stat', 'pvalue', 'padj'}
NATIVE = {'method', 'n_significant_genes', 'samples_per_group', 'thresholds', 'n_stable_genes',
          'stable_gene_fraction', 'median_minimum_effect_retention', 'genes'}
PLAUS = {'n_significant', 'n_extreme_lfc', 'frac_extreme_lfc', 'pct_up', 'pct_down',
         'median_abs_log2fc', 'extreme_lfc_threshold'}
FORBIDDEN_KEYS = {'gold', 'verdict', 'reply', 'claim_violations', 'false_discovery',
                  'inference_state', 'admissible', 'licensed_claim', 'biological_correctness',
                  'expected_outcome', 'opportunities', 'source_path', 'provenance', 'allocation_id',
                  'donor_ids', 'sample_id', 'mapping_source', 'source_sha256', 'warning_sha256',
                  'age', 'sex', 'demographics', 'collection_date', 'raw_counts'}


def pointer(parts):
    return '/' + '/'.join(str(x).replace('~', '~0').replace('/', '~1') for x in parts)


def leaves(x, path=()):
    if isinstance(x, dict) and x:
        for k, v in x.items():
            yield from leaves(v, path + (k,))
    elif isinstance(x, list) and x:
        for i, v in enumerate(x):
            yield from leaves(v, path + (i,))
    else:
        yield path, x


def keys(x):
    if isinstance(x, dict):
        for k, v in x.items():
            yield k
            yield from keys(v)
    elif isinstance(x, list):
        for v in x:
            yield from keys(v)


def allowed(obj, names):
    assert isinstance(obj, dict) and set(obj) <= names, 'Unexpected input schema; export blocked'


def warning_text(text):
    # Retain library/module/line, warning class and exact scientific message.
    if text.startswith('/'):
        assert '/site-packages/' in text, 'Unrecognized warning path; manual review required'
        return text.split('/site-packages/', 1)[1]
    assert '/' not in text or not re.search(r'/(Users|home|private|tmp)/', text)
    return text


def donor_ids(packet):
    ids = set()
    for values in packet['design'].get('donor_ids', {}).values():
        ids.update(values)
    paired = packet['paired_donor_sensitivity']
    if 'status' not in paired:
        ids.update(paired)
    checks = packet['inference_eligibility_evidence'].get('design_check_facts') or {}
    for association in checks.get('confounding_associations', {}).values():
        ids.update(association.get('table', {}))
    return ids


def aliases_for(packet):
    # CSPRNG, independently per case. No deterministic hash of source identifiers.
    paired = packet['paired_donor_sensitivity']
    donor = {} if 'status' in paired else {k: 'pair_' + secrets.token_hex(12) for k in paired}
    covariates = [x for x in ['pool', 'sex', 'age'] if re.search(r'\b' + x + r'\b', packet['design']['formula'])]
    return {'case_alias': 'context_' + secrets.token_hex(12), 'donors': donor,
            'design_labels': {k: f'adjustment_{i + 1}' for i, k in enumerate(covariates)} | {'donor_id': 'pair'}}


def sanitized(packet, mapping):
    """Allowlist projection plus a complete source-leaf -> export-leaf local audit."""
    allowed(packet, TOP)
    allowed(packet['design'], DESIGN)
    allowed(packet['statistics'], STATS)
    allowed(packet['native_stability_facts'], NATIVE)
    allowed(packet['plausibility_facts'], PLAUS)
    audit_map = {}

    def take(value, src, dst=None, transform=None):
        dst = src if dst is None else dst
        result = transform(value) if transform else copy.deepcopy(value)
        old_leaves, new_leaves = list(leaves(value, src)), list(leaves(result, dst))
        assert len(old_leaves) == len(new_leaves)
        for (a, av), (b, bv) in zip(old_leaves, new_leaves):
            audit_map[a] = {'destination': pointer(b), 'action': 'KEEP' if av == bv else 'TRANSFORM',
                            'source_value_sha256': digest(av), 'export_value_sha256': digest(bv)}
        return result

    def warn(rows, src, dst=None):
        dst = src if dst is None else dst
        out = []
        for i, w in enumerate(rows):
            allowed(w, {'text', 'count'})
            out.append({'text': take(w['text'], src + (i, 'text'), dst + (i, 'text'), warning_text),
                        'count': take(w['count'], src + (i, 'count'), dst + (i, 'count'))})
        if not rows:
            take(rows, src, dst)
        return out

    out = {}
    for k in ['cell_type', 'biological_condition', 'statistics', 'plausibility_facts', 'warning_scope', 'limitations']:
        out[k] = take(packet[k], (k,))
    for row in out['statistics']['rows']:
        allowed(row, ROW)
    out['case_id'] = take(packet['case_id'], ('case_id',), transform=lambda _: mapping['case_alias'])
    # Source cohort names/filenames are not necessary; species is scientifically relevant.
    out['dataset'] = take(packet['dataset'], ('dataset',), transform=lambda _: 'mouse cohort' if packet['case_id'].startswith('F1_') else 'human cohort')
    out['perturbation_identity'] = {}
    allowed(packet['perturbation_identity'], {'symbol', 'gene_id', 'mapping_source'})
    for k in ['symbol', 'gene_id']:
        if k in packet['perturbation_identity']:
            out['perturbation_identity'][k] = take(packet['perturbation_identity'][k], ('perturbation_identity', k))
    if not packet['perturbation_identity']:
        take({}, ('perturbation_identity',))
    out['design'] = {}
    for k, v in packet['design'].items():
        if k in {'allocation_id', 'donor_ids'}:
            continue
        if k == 'formula':
            def relabel(s):
                for old, new in mapping['design_labels'].items():
                    s = re.sub(r'\b' + re.escape(old) + r'\b', new, s)
                return s
            out['design'][k] = take(v, ('design', k), transform=relabel)
        else:
            out['design'][k] = take(v, ('design', k))
    selected = {r['gene'] for r in out['statistics']['rows']}
    out['native_stability_facts'] = {}
    for k, v in packet['native_stability_facts'].items():
        if k != 'genes':
            out['native_stability_facts'][k] = take(v, ('native_stability_facts', k))
        else:
            rows = []
            for i, row in enumerate(v):
                allowed(row, {'gene', 'full_log2cpm_effect', 'minimum_effect_retention'})
                if row['gene'] in selected:
                    rows.append(take(row, ('native_stability_facts', 'genes', i), ('native_stability_facts', 'genes', len(rows))))
            out['native_stability_facts'][k] = rows
    out['count_integrity'] = {}
    if packet['count_integrity']:
        allowed(packet['count_integrity'], {'valid', 'source', 'n_nonzero', 'max_count'})
        for k in ['valid', 'source']:
            out['count_integrity'][k] = take(packet['count_integrity'][k], ('count_integrity', k))
    e = packet['inference_eligibility_evidence']
    allowed(e, {'source_fit_completed', 'independent_numerical_validation', 'design_check_facts', 'missingness'})
    out['inference_eligibility_evidence'] = {k: take(e[k], ('inference_eligibility_evidence', k)) for k in e if k != 'design_check_facts'}
    checks = e['design_check_facts']
    if checks is None:
        out['inference_eligibility_evidence']['design_check_facts'] = take(None, ('inference_eligibility_evidence', 'design_check_facts'))
    else:
        clean_checks = {}
        for k in ['replicates_per_group', 'min_cells_per_sample', 'minimum_replicates_per_group']:
            clean_checks[k] = take(checks[k], ('inference_eligibility_evidence', 'design_check_facts', k))
        clean_checks['design_validation'] = {}
        for k in ['n_samples', 'rank', 'n_columns', 'full_rank']:
            path = ('inference_eligibility_evidence', 'design_check_facts', 'design_validation', k)
            clean_checks['design_validation'][k] = take(checks['design_validation'][k], path)
        out['inference_eligibility_evidence']['design_check_facts'] = clean_checks
    paired = packet['paired_donor_sensitivity']
    if 'status' in paired:
        allowed(paired, {'status', 'reason'})
        out['paired_donor_sensitivity'] = take(paired, ('paired_donor_sensitivity',))
    else:
        out['paired_donor_sensitivity'] = {}
        for original, value in paired.items():
            allowed(value, {'rows', 'warnings', 'source_sha256', 'warning_sha256'})
            alias = mapping['donors'][original]
            src, dst = ('paired_donor_sensitivity', original), ('paired_donor_sensitivity', alias)
            for row in value['rows']:
                allowed(row, {'gene', 'log2FoldChange', 'lfcSE', 'pvalue', 'padj'})
                assert row['gene'] in selected
            out['paired_donor_sensitivity'][alias] = {'rows': take(value['rows'], src + ('rows',), dst + ('rows',)),
                                                     'warnings': warn(value['warnings'], src + ('warnings',), dst + ('warnings',))}
    out['numerical_warnings'] = warn(packet['numerical_warnings'], ('numerical_warnings',))
    out['export_context'] = {
        'version': VERSION,
        'design_label_notice': 'Adjustment labels are privacy-minimized aliases; original variable meanings and individual values are not supplied. Formula structure, pairing and numerical estimates are unchanged.',
        'sensitivity_label_notice': 'Pair aliases identify omissions within this context only; aliases cannot be joined across contexts.',
        'diagnostic_scope': 'Native genome-wide aggregate diagnostics retained; individual gene diagnostic rows restricted to the registered common gene view. Other gene names and source provenance omitted.',
        'privacy_limit': 'Small-cohort and omission estimates are derived research data, not guaranteed anonymous data.'}
    assert_no_leak(out, packet)
    audit = []
    for path, value in leaves(packet):
        record = audit_map.get(path)
        if record is None:
            record = {'destination': None, 'action': 'EXCLUDE', 'source_value_sha256': digest(value),
                      'reason': exclusion_reason(path)}
        audit.append({'source': pointer(path), **record})
    destinations = {r['destination'] for r in audit if r['destination']}
    for path, value in leaves(out):
        if pointer(path) not in destinations:
            audit.append({'source': None, 'destination': pointer(path), 'action': 'ADD_DISCLOSURE_OR_EMPTY_CONTAINER', 'export_value_sha256': digest(value)})
    return out, audit


def exclusion_reason(path):
    if path[0] in {'provenance', 'dataset'} or 'mapping_source' in path or any(str(p).endswith('sha256') for p in path):
        return 'Source provenance/machine linkage unnecessary for reporting; retained locally'
    if path[0] in {'observed_significant_gene_ids', 'native_stability_facts'}:
        return 'Outside frozen common numerical-gene view; aggregate counts preserved'
    if path[0] == 'count_integrity':
        return 'Raw-matrix extrema/size unnecessary; raw-count validity/source retained'
    return 'Individual identifiers, encoded design levels or redundant source metadata; aggregate design/pairing preserved'


def assert_no_leak(out, original):
    assert not FORBIDDEN_KEYS.intersection(keys(out)), 'Forbidden reporter field'
    text = encode(out)
    assert not re.search(r'/Users/|/home/|/private/|\.h5ad|CE\d{7}|\b\d{4}-\d{2}-\d{2}\b|AIza[\w-]{20,}', text), 'Identifying/path/date/credential-like content'
    for identifier in donor_ids(original):
        assert identifier not in text, 'Source donor identifier in export'
    assert original['case_id'] not in text
    assert not re.search(r'\b(age|sex|donor_id|sample_id)\b', out['design']['formula'])


def policy_signature(private):
    from agent.inference_state import apply_inference_state
    from agent.output_schema import build_output_schema
    result = apply_inference_state('run_deseq2', copy.deepcopy(private['tool']), private['args'])
    schema = build_output_schema('run_deseq2', result, private['args'])
    return {k: schema.get(k) for k in ['inference_state', 'allowed_interpretation_level', 'result_withheld', 'forbidden_inference_flags', 'stat_result']}


def local_d_input(packet, original_private):
    # Keep the original cached policy diagnostics local. They are never an API input.
    # The frozen renderer uses these cached policy outputs; extra metadata is the
    # sanitized common packet. No paired-sensitivity evidence enters policy inputs.
    private = copy.deepcopy(original_private)
    assert private['tool']['results'] == packet['statistics']['rows']
    return private


def make_request(packet, arm):
    assert arm in ('A', 'B')
    return {'model': MODEL, 'contents': REQUEST + '\n\nCANONICAL EVIDENCE:\n' + encode(packet),
            'config': {'system_instruction': PROMPTS[arm], **MODEL_CONFIG}}


def original_preservation():
    verify_lock()
    m = read(OUT / 'E2_BLOCKED_SNAPSHOT_MANIFEST.json')['files']
    assert all(sha(ROOT / p) == h for p, h in m.items()), 'E2 snapshot mismatch'
    assert not (OUT / 'execution').exists(), 'E2 execution already exists; stop'
    return {'e2_snapshot_entries': len(m), 'e2_snapshot_sha256': sha(OUT / 'E2_BLOCKED_SNAPSHOT_MANIFEST.json'),
            'e2_mismatches': 0, 'earlier_work': preservation()}


def main():
    before = original_preservation()
    # Docs may already exist. Generated subdirectories are exclusive; no regeneration.
    os.umask(0o077)
    for sub in ['candidate_packets', 'candidate_requests', 'local_only']:
        (DEST / sub).mkdir(parents=True, exist_ok=False)
    source_manifest = [__import__('json').loads(l) for l in (OUT / 'E2_CASE_MANIFEST.jsonl').read_text().splitlines()]
    records, mapping_records, field_audits = [], {}, {}
    for item in source_manifest:
        case = item['case_id']
        original = read(ROOT / item['packet_path'])
        mapping = aliases_for(original)
        packet, audit = sanitized(original, mapping)
        alias = mapping['case_alias']
        packet_path = DEST / 'candidate_packets' / f'{alias}.json'
        write(packet_path, packet)
        mapping_records[case] = mapping
        field_audits[case] = audit
        private = read(OUT / 'arm_d_inputs' / f'{case}.json')
        signature = policy_signature(private)
        assert signature == policy_signature(local_d_input(packet, private))
        requests = {}
        for arm in 'AB':
            p = DEST / 'candidate_requests' / f'{alias}_{arm}.json'
            write(p, make_request(packet, arm))
            requests[arm] = {'file': str(p.relative_to(DEST)), 'sha256': sha(p)}
        records.append({'source_case': case, 'export_case': alias, 'original_packet_sha256': sha(ROOT / item['packet_path']),
                        'original_content_sha256': digest(original), 'sanitized_packet_sha256': sha(packet_path),
                        'sanitized_content_sha256': digest(packet), 'packet_file': str(packet_path.relative_to(DEST)),
                        'arm_scientific_input_hashes': {arm: digest(packet) for arm in 'ABCD'},
                        'arm_d_local_policy_input_sha256': sha(OUT / 'arm_d_inputs' / f'{case}.json'),
                        'gate_signature': signature, 'requests': requests,
                        'transformation': VERSION, 'actual_transmissions': 0})
    write(DEST / 'local_only' / 'SOURCE_ALIAS_MAP.json', mapping_records)
    write(DEST / 'local_only' / 'FIELD_LEVEL_AUDIT.json', field_audits)
    write(DEST / 'local_only' / 'CASE_TRANSFER_LEDGER.json', records)
    order = read(OUT / 'E2_EXECUTION_ORDER.json')['order']
    write(DEST / 'local_only' / 'PROPOSED_DISPATCH_ORDER.json', [
        {'case_id': mapping_records[r['case_id']]['case_alias'], 'arm': r['arm']} for r in order])
    write(DEST / 'PRESERVATION_BEFORE.json', before)
    write(DEST / 'PRESERVATION_AFTER_PREPARATION.json', original_preservation())
    write(DEST / 'PREPARATION_STATUS.json', {'time': now(), 'status': 'E2_BLOCKED', 'packets': len(records),
          'candidate_reporting_requests': 2 * len(records), 'reporting_requests_sent': 0, 'new_scored_responses': 0,
          'billing_project_verified': False, 'institutional_and_dua_permission_verified': False,
          'explicit_sanitized_transfer_approval_received': False, 'sdk_clients_created': 0,
          'service_type_intended': 'Gemini Developer API; active billed project for current credential NOT VERIFIED',
          'export_directory_upload_permitted': False,
          'required_future_execution': 'New approved sanitized-input wrapper; original execute.py is not authorized.'})
    print(encode({'status': 'E2_BLOCKED', 'prepared_packets': len(records), 'candidate_requests': 2 * len(records), 'sent': 0}))


if __name__ == '__main__':
    main()
