"""Local preparation tests; real cases are inspected, never rendered or scored."""
import copy
import json
import stat
import unittest
from unittest.mock import patch

from common import OUT, ROOT, MODEL, read, sha, digest, encode
from reporters import PROMPTS, REQUEST, MODEL_CONFIG, firewall
from test_e2 import fixture, private
from prepare import supported_rows
from privacy_export import (DEST, aliases_for, sanitized, warning_text, donor_ids, leaves,
                           pointer, assert_no_leak, make_request, policy_signature, local_d_input,
                           original_preservation)


class PrivacyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ledger = read(DEST / 'local_only/CASE_TRANSFER_LEDGER.json')
        cls.maps = read(DEST / 'local_only/SOURCE_ALIAS_MAP.json')
        cls.audit = read(DEST / 'local_only/FIELD_LEVEL_AUDIT.json')
        cls.pairs = [(r, read(OUT / 'packets' / f'{r["source_case"]}.json'), read(DEST / r['packet_file'])) for r in cls.ledger]

    def test_fixed_frame(self):
        self.assertEqual(len(self.pairs), 102)
        self.assertEqual(len(list((DEST / 'candidate_requests').glob('*.json'))), 204)
        self.assertEqual(len({r['export_case'] for r, _, _ in self.pairs}), 102)

    def test_numerical_evidence_exact(self):
        for _, original, exported in self.pairs:
            self.assertEqual(original['statistics'], exported['statistics'])
            self.assertEqual(original['plausibility_facts'], exported['plausibility_facts'])
            self.assertEqual(supported_rows(original), supported_rows(exported))
        self.assertEqual(sum(len(supported_rows(p)) for _, _, p in self.pairs), 149)

    def test_target_mappings(self):
        targets = 0
        for _, original, exported in self.pairs:
            if original['perturbation_identity']:
                targets += 1
                for k in ['symbol', 'gene_id']:
                    self.assertEqual(original['perturbation_identity'][k], exported['perturbation_identity'][k])
                gene = exported['perturbation_identity']['gene_id']
                self.assertTrue(any(r['gene'] == gene for r in exported['statistics']['rows']))
        self.assertEqual(targets, 9)

    def test_primary_warning_messages_and_counts(self):
        for _, original, exported in self.pairs:
            self.assertEqual(exported['numerical_warnings'], [
                {'text': warning_text(w['text']), 'count': w['count']} for w in original['numerical_warnings']])
            self.assertEqual(original['warning_scope'], exported['warning_scope'])
            self.assertEqual(original['limitations'], exported['limitations'])

    def test_paired_sensitivity_exact_under_local_aliases(self):
        total = 0
        for r, original, exported in self.pairs:
            paired = original['paired_donor_sensitivity']
            if 'status' in paired:
                self.assertEqual(paired, exported['paired_donor_sensitivity'])
                continue
            mapping = self.maps[r['source_case']]['donors']
            self.assertEqual(len(mapping), len(paired))
            for source, alias in mapping.items():
                total += 1
                a, b = paired[source], exported['paired_donor_sensitivity'][alias]
                self.assertEqual(a['rows'], b['rows'])
                self.assertEqual(b['warnings'], [{'text': warning_text(w['text']), 'count': w['count']} for w in a['warnings']])
        self.assertEqual(total, 24)

    def test_aliases_are_case_local_random_and_private(self):
        aliases = [v for m in self.maps.values() for v in m['donors'].values()]
        self.assertEqual(len(aliases), len(set(aliases)))
        self.assertEqual(stat.S_IMODE((DEST / 'local_only/SOURCE_ALIAS_MAP.json').stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE((DEST / 'local_only').stat().st_mode), 0o700)
        original = next(p for _, p, _ in self.pairs if 'status' not in p['paired_donor_sensitivity'])
        self.assertNotEqual(aliases_for(original), aliases_for(original))

    def test_design_values_preserved(self):
        for r, original, exported in self.pairs:
            for k, v in original['design'].items():
                if k not in {'formula', 'allocation_id', 'donor_ids'}:
                    self.assertEqual(exported['design'][k], v)
            self.assertEqual(original['design']['formula'].count('+'), exported['design']['formula'].count('+'))
            for k in ['source_fit_completed', 'independent_numerical_validation', 'missingness']:
                self.assertEqual(original['inference_eligibility_evidence'][k], exported['inference_eligibility_evidence'][k])

    def test_native_summaries_and_selected_diagnostics(self):
        for _, original, exported in self.pairs:
            for k, value in original['native_stability_facts'].items():
                if k != 'genes':
                    self.assertEqual(value, exported['native_stability_facts'][k])
                else:
                    genes = {r['gene'] for r in exported['statistics']['rows']}
                    self.assertEqual([r for r in value if r['gene'] in genes], exported['native_stability_facts'][k])

    def test_four_arm_planned_input_parity_and_request_body(self):
        for r, _, exported in self.pairs:
            self.assertEqual(set(r['arm_scientific_input_hashes'].values()), {digest(exported)})
            for arm in 'AB':
                req = read(DEST / r['requests'][arm]['file'])
                self.assertEqual(req, make_request(exported, arm))
                self.assertEqual(req['contents'], REQUEST + '\n\nCANONICAL EVIDENCE:\n' + encode(exported))
                self.assertEqual(req['config'], {'system_instruction': PROMPTS[arm], **MODEL_CONFIG})
                self.assertEqual(req['model'], MODEL)
                self.assertEqual(set(req), {'model', 'contents', 'config'})

    def test_no_identifiers_gold_or_raw_observations(self):
        for r, original, exported in self.pairs:
            assert_no_leak(exported, original)
            for arm in 'AB':
                serialized = encode(read(DEST / r['requests'][arm]['file']))
                for identifier in donor_ids(original):
                    self.assertNotIn(identifier, serialized)
                self.assertNotIn('SOURCE_ALIAS_MAP', serialized)
                self.assertNotIn('CASE_TRANSFER_LEDGER', serialized)

    def test_fail_closed_new_field(self):
        _, original, _ = self.pairs[0]
        p = copy.deepcopy(original)
        p['unexpected_demographic'] = 'CANARY'
        with self.assertRaises(AssertionError):
            sanitized(p, aliases_for(p))

    def test_fail_closed_gold_label(self):
        _, original, _ = self.pairs[0]
        p = copy.deepcopy(original)
        p['statistics']['gold'] = 'CANARY'
        with self.assertRaises(AssertionError):
            sanitized(p, aliases_for(p))

    def test_fail_closed_donor_in_free_text(self):
        _, original, _ = self.pairs[0]
        p = copy.deepcopy(original)
        p['limitations'].append(next(iter(donor_ids(p))))
        with self.assertRaises(AssertionError):
            sanitized(p, aliases_for(p))

    def test_frozen_gate_decisions_all_contexts(self):
        for r, _, exported in self.pairs:
            original_private = read(OUT / 'arm_d_inputs' / f'{r["source_case"]}.json')
            self.assertEqual(r['gate_signature'], policy_signature(original_private))
            self.assertEqual(r['gate_signature'], policy_signature(local_d_input(exported, original_private)))

    def test_synthetic_license_withholding(self):
        p = fixture()
        p['paired_donor_sensitivity'] = {'pair_synthetic': {'rows': p['statistics']['rows'], 'warnings': []}}
        text, trace = firewall(p, private(p, 'suspect'))
        self.assertTrue(trace['original_schema']['result_withheld'])
        self.assertNotIn('TEST000', text)
        self.assertNotIn('pair_synthetic', text)

    def test_synthetic_blocked_no_scientific_supplement(self):
        p = fixture()
        d = private(p)
        d['tool']['admissibility'] = {'admissible': False, 'blocked_reasons': ['synthetic:block'], 'checks': {}}
        d['tool']['error'] = 'inadmissible_inference'
        text, trace = firewall(p, d)
        self.assertEqual(trace['original_schema']['inference_state'], 'BLOCKED')
        self.assertNotIn('TEST000', text)
        self.assertNotIn('0.001', text)

    def test_sensitivity_never_sent_to_policy(self):
        r, _, packet = self.pairs[-1]
        d = read(OUT / 'arm_d_inputs' / f'{r["source_case"]}.json')
        other = copy.deepcopy(packet)
        other['paired_donor_sensitivity'] = {'UNTRUSTED_NEW_EVIDENCE': True}
        self.assertEqual(local_d_input(packet, d), local_d_input(other, d))

    def test_field_audit_is_complete(self):
        for r, original, exported in self.pairs:
            audit = self.audit[r['source_case']]
            sources = [a['source'] for a in audit if a['source'] is not None]
            self.assertEqual(set(sources), {pointer(p) for p, _ in leaves(original)})
            self.assertEqual(len(sources), len(set(sources)))
            destinations = {a['destination'] for a in audit if a['destination'] is not None}
            self.assertEqual(destinations, {pointer(p) for p, _ in leaves(exported)})

    def test_file_and_content_hashes(self):
        for r, original, exported in self.pairs:
            self.assertEqual(sha(OUT / 'packets' / f'{r["source_case"]}.json'), r['original_packet_sha256'])
            self.assertEqual(sha(DEST / r['packet_file']), r['sanitized_packet_sha256'])
            self.assertEqual(digest(original), r['original_content_sha256'])
            self.assertEqual(digest(exported), r['sanitized_content_sha256'])
            for req in r['requests'].values():
                self.assertEqual(sha(DEST / req['file']), req['sha256'])

    def test_no_execution_and_permission_still_blocked(self):
        status = read(DEST / 'PREPARATION_STATUS.json')
        self.assertEqual(status['status'], 'E2_BLOCKED')
        for k in ['billing_project_verified', 'institutional_and_dua_permission_verified', 'explicit_sanitized_transfer_approval_received']:
            self.assertFalse(status[k])
        self.assertEqual(status['reporting_requests_sent'], 0)
        self.assertFalse((OUT / 'execution').exists())
        self.assertFalse((DEST / 'execution').exists())

    def test_original_preservation(self):
        self.assertEqual(original_preservation()['e2_mismatches'], 0)


if __name__ == '__main__':
    unittest.main()
