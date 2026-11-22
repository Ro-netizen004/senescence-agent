"""Real input inspection; synthetic-only renderer/SDK serialization tests."""
import copy
from types import SimpleNamespace
import unittest
from common import OUT, read, sha, digest
from privacy_export import DEST as EXPORT, make_request, policy_signature
from reporters import MODEL_CONFIG, PROMPTS
from test_e2 import fixture, private
from integration import (DEST, MODEL, CONFIG, verify_export, amended_request, route,
                         sdk_arguments, response_status, local_report, require_clearance)


class AmendmentTests(unittest.TestCase):
    def test_privacy_lock_preserved(self):
        self.assertEqual(len(verify_export()['files']), 327)

    def test_only_model_changed_all_204(self):
        for rec in read(EXPORT / 'local_only/CASE_TRANSFER_LEDGER.json'):
            for arm in 'AB':
                old = read(EXPORT / rec['requests'][arm]['file'])
                new = read(DEST / 'requests' / (rec['export_case'] + '_' + arm + '.json'))
                self.assertEqual(new, amended_request(old))
                self.assertEqual(new['contents'], old['contents'])
                self.assertEqual(new['config'], {'system_instruction': PROMPTS[arm], **MODEL_CONFIG})

    def test_all_408_routes_and_gate_signatures(self):
        for rec in read(EXPORT / 'local_only/CASE_TRANSFER_LEDGER.json'):
            routes = {a: route(rec, a) for a in 'ABCD'}
            self.assertEqual(len({r['packet_content_sha256'] for r in routes.values()}), 1)
            self.assertEqual(policy_signature(routes['D']['private']), rec['gate_signature'])
            for a in 'ABC':
                self.assertIsNone(routes[a]['private'])
            for a in 'CD':
                self.assertIsNone(routes[a]['request'])

    def test_sdk_config_synthetic_only(self):
        req = amended_request(make_request(fixture(), 'B'))
        args = sdk_arguments(req)
        self.assertEqual(set(args), {'model', 'contents', 'config'})
        self.assertEqual(args['model'], MODEL)
        self.assertEqual(args['contents'], req['contents'])
        self.assertEqual(args['config'].model_dump(exclude_none=True), req['config'])
        self.assertIsNone(args['config'].tools)

    def test_reject_unknown_model_and_field(self):
        req = amended_request(make_request(fixture(), 'A'))
        for changed in ({**req, 'model': 'gemini-3.5-flash'}, {**req, 'private': {}}):
            with self.assertRaises(ValueError):
                sdk_arguments(changed)

    def test_backend_mismatch_including_missing_fails_closed(self):
        for actual in (None, 'gemini-3.5-flash', 'gemini-other'):
            self.assertEqual(response_status(SimpleNamespace(model_version=actual)), 'MODEL_MISMATCH')

    def test_response_status_synthetic(self):
        r = SimpleNamespace(model_version=MODEL, text='synthetic', candidates=[])
        self.assertEqual(response_status(r), 'SUCCESS')
        r.text = ''
        self.assertEqual(response_status(r), 'EMPTY_RESPONSE')
        r.candidates = [SimpleNamespace(finish_reason='MAX_TOKENS')]
        self.assertEqual(response_status(r), 'TRUNCATED_RESPONSE')

    def test_synthetic_c_d_no_mutation_and_withholding(self):
        p = fixture(); h = digest(p)
        self.assertIn('TEST000', local_report('C', p)[0])
        text, trace = local_report('D', p, private(p, 'suspect'))
        self.assertTrue(trace['original_schema']['result_withheld'])
        self.assertNotIn('TEST000', text)
        self.assertEqual(h, digest(p))

    def test_synthetic_blocked_and_warning(self):
        p = fixture(); p['numerical_warnings'] = [{'text': 'SYNTHETIC_WARNING', 'count': 1}]
        self.assertIn('SYNTHETIC_WARNING', local_report('C', p)[0])
        d = private(p); d['tool']['error'] = 'inadmissible_inference'
        d['tool']['admissibility'] = {'admissible': False, 'blocked_reasons': ['dummy'], 'checks': {}}
        text, trace = local_report('D', p, d)
        self.assertEqual(trace['original_schema']['inference_state'], 'BLOCKED')
        self.assertNotIn('TEST000', text)

    def test_dispatch_identical_and_limits_frozen(self):
        self.assertEqual(read(DEST / 'EXECUTION_ORDER.json'), read(OUT / 'E2_EXECUTION_ORDER.json'))
        self.assertEqual(CONFIG['max_api_calls'], 204)
        self.assertEqual(CONFIG['sdk_attempts'], 1)
        self.assertEqual(CONFIG['application_retries'], 0)
        self.assertEqual(CONFIG['max_concurrent_jobs'], 2)

    def test_preparation_does_not_authorize_execution(self):
        for receipt in (None, {}, {'explicit_final_execution_approval': True}):
            with self.assertRaises(PermissionError):
                require_clearance(receipt, 'synthetic-protocol-hash')
        self.assertFalse((DEST / 'execution').exists())
        self.assertFalse((OUT / 'execution').exists())
        self.assertFalse(read(DEST / 'PREPARATION_STATUS.json')['final_execution_approval'])


if __name__ == '__main__':
    unittest.main()
