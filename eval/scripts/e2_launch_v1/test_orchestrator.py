"""No SDK client, network, research responses, or scoring. Dummy data only."""
import copy
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from google.genai import types
from common import read, sha
from integration import amended_request
from privacy_export import make_request
from test_e2 import fixture, private
from orchestrator import (run_frame, run_slot, planning_tokens, usage_cost, price,
                          seal, verify_manifest, validate_clearance, MODEL)


def dummy_response(text='SYNTHETIC_ONLY', model=MODEL, usage=True, reason='STOP'):
    return types.GenerateContentResponse(model_version=model,
        candidates=[types.Candidate(content=types.Content(parts=[types.Part(text=text)]), finish_reason=reason)],
        usage_metadata=types.GenerateContentResponseUsageMetadata(prompt_token_count=100,
            candidates_token_count=20, thoughts_token_count=10, total_token_count=130) if usage else None)


class FakeClock:
    def __init__(self): self.t = 0; self.waits = []
    def now(self): return self.t
    def sleep(self, n): self.waits.append(n); self.t += n


class LaunchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / 'run'
        self.clock = FakeClock()
        self.calls = []

    def tearDown(self): self.temp.cleanup()

    def loader(self, item):
        p = fixture()
        return {'packet': p, 'request': amended_request(make_request(p, item['arm'])) if item['arm'] in 'AB' else None,
                'private': private(p) if item['arm'] == 'D' else None,
                'canonical_sha256': 'SYNTHETIC', 'gate_signature': 'SYNTHETIC'}

    def sender(self, request):
        self.calls.append(copy.deepcopy(request))
        return dummy_response()

    def order(self, n=1, arms='ABCD'):
        return [{'case_id': f'SYNTHETIC_{i}', 'arm': a} for i in range(n) for a in arms]

    def run_dummy(self, order=None, send=None, **kwargs):
        order = order or self.order()
        reserve = {(i['case_id'], i['arm']): planning_tokens(self.loader(i)['request']) for i in order if i['arm'] in 'AB'}
        defaults = dict(budget=5, rpm=2, tpm=100000, rpd_remaining=204,
                        sleep=self.clock.sleep, clock=self.clock.now, classification='SYNTHETIC_ONLY')
        defaults.update(kwargs)
        return run_frame(order, self.root, self.loader, send or self.sender, reserve, **defaults)

    def test_full_408_slots_204_calls_no_retry(self):
        result = self.run_dummy(self.order(102))
        self.assertEqual(result['completed_slots'], 408)
        self.assertEqual(result['api_attempts'], 204)
        self.assertEqual(len(self.calls), 204)
        self.assertEqual(result['retries'], 0)
        self.assertEqual(result['status'], 'SYNTHETIC_TEST_ONLY')
        self.assertTrue(all(x == 61 for x in self.clock.waits))
        verify_manifest(self.root)

    def test_exact_request_body_no_private_context(self):
        self.run_dummy()
        expected = [amended_request(make_request(fixture(), arm)) for arm in 'AB']
        for req in self.calls:
            self.assertIn(req, expected)
            self.assertEqual(set(req), {'model', 'contents', 'config'})
        for arm in 'ABCD':
            slot = self.root / ('SYNTHETIC_0_' + arm)
            verify_manifest(slot)
            self.assertEqual(read(slot / 'REPORTER_VISIBLE_PACKET.json'), fixture())

    def test_response_capture_and_thinking_cost(self):
        r = self.run_dummy()
        self.assertAlmostEqual(r['known_usage_estimated_usd'], 2 * price(100, 30))
        p = self.root / 'SYNTHETIC_0_A'
        self.assertEqual(read(p / 'PROVIDER_RESPONSE.json')['model_version'], MODEL)
        self.assertEqual(read(p / 'RESPONSE.json')['text'], 'SYNTHETIC_ONLY')

    def test_missing_usage_not_zero(self):
        r = self.run_dummy(send=lambda req: dummy_response(usage=False))
        self.assertEqual(r['unknown_cost_attempts'], 2)
        self.assertGreater(r['budget_planning_accounted_usd'], 0)
        self.assertIsNone(read(self.root / 'SYNTHETIC_0_A/RESPONSE.json')['estimated_usd'])

    def test_auth_failure_finish_batch_no_secret_exception(self):
        class ApiError(Exception): code = 403
        def fail(req): raise ApiError('SECRET_CANARY must not appear')
        r = self.run_dummy(self.order(2), send=fail)
        self.assertEqual(r['reason'], 'AUTHENTICATION_OR_PERMISSION_FAILURE')
        self.assertEqual(r['completed_slots'], 2)
        self.assertEqual(r['api_attempts'], 2)
        self.assertEqual(len(r['incomplete']), 6)
        for f in self.root.rglob('*.json'):
            self.assertNotIn('SECRET_CANARY', f.read_text())

    def test_three_api_errors_stop_after_batch_without_retries(self):
        class ApiError(Exception): code = 429
        def fail(req): raise ApiError()
        r = self.run_dummy(self.order(3, 'AB'), send=fail)
        self.assertEqual(r['api_attempts'], 4)
        self.assertEqual(r['reason'], 'THREE_CONSECUTIVE_API_FAILURES')
        self.assertEqual(r['retries'], 0)

    def test_empty_response_counts_as_failure(self):
        r = self.run_dummy(self.order(3, 'AB'), send=lambda req: dummy_response(text=''))
        self.assertEqual(r['reason'], 'THREE_CONSECUTIVE_API_FAILURES')

    def test_wrong_backend_preserved_and_halts(self):
        r = self.run_dummy(self.order(2), send=lambda req: dummy_response(model='different'))
        self.assertEqual(r['reason'], 'MODEL_MISMATCH')
        rec = read(self.root / 'SYNTHETIC_0_A/RESPONSE.json')
        self.assertEqual(rec['actual_backend'], 'different')
        self.assertEqual(rec['text'], 'SYNTHETIC_ONLY')

    def test_truncation_preserved_not_replaced(self):
        r = self.run_dummy(send=lambda req: dummy_response(reason='MAX_TOKENS'))
        self.assertEqual(r['api_attempts'], 2)
        self.assertEqual(read(self.root / 'SYNTHETIC_0_A/RESPONSE.json')['status'], 'TRUNCATED_RESPONSE')

    def test_budget_preflight_preserves_block_and_sends_nothing(self):
        with self.assertRaises(PermissionError): self.run_dummy(budget=.001)
        self.assertEqual(self.calls, [])
        self.assertEqual(read(self.root / 'PREFLIGHT_BLOCKED.json')['status'], 'PREFLIGHT_BLOCKED')
        verify_manifest(self.root)

    def test_budget_overrun_stops_no_case_substitution(self):
        def costly(req):
            r = dummy_response()
            r.usage_metadata.prompt_token_count = 100000000
            return r
        r = self.run_dummy(self.order(2), send=costly)
        self.assertEqual(r['reason'], 'BUDGET_PLANNING_STOP')
        self.assertEqual(r['completed_slots'], 2)
        self.assertEqual(len(r['incomplete']), 6)

    def test_quota_preflight_blocks_no_sends(self):
        with self.assertRaises(PermissionError): self.run_dummy(rpd_remaining=1)
        self.assertEqual(self.calls, [])

    def test_tpm_preflight_blocks(self):
        with self.assertRaises(PermissionError): self.run_dummy(tpm=1)
        self.assertEqual(self.calls, [])

    def test_exclusive_output_no_resume(self):
        self.run_dummy(); before = sha(self.root / 'SHA256_MANIFEST.json')
        with self.assertRaises(FileExistsError): self.run_dummy()
        self.assertEqual(sha(self.root / 'SHA256_MANIFEST.json'), before)

    def test_manifest_tampering_detected(self):
        self.run_dummy()
        p = self.root / 'SUMMARY.json'
        self.assertEqual(p.stat().st_mode & 0o777, 0o400)
        p.chmod(0o600)
        p.write_text('{}')
        with self.assertRaises(ValueError): verify_manifest(self.root)

    def test_missing_clearance_before_any_client(self):
        for receipt in ({}, {'protocol_sha256': 'wrong'}, {'explicit_final_execution_approval': True}):
            with self.assertRaises(PermissionError): validate_clearance(receipt)

    def test_local_render_failure_preserved(self):
        def fail(*args): raise ValueError('dummy renderer error')
        r = self.run_dummy(self.order(2, 'CD'), render=fail)
        self.assertEqual(r['reason'], 'LOCAL_INFRASTRUCTURE_FAILURE')
        self.assertEqual(r['api_attempts'], 0)
        verify_manifest(self.root)

    def test_interruption_preserves_reserved_incomplete(self):
        def interrupt(req): raise KeyboardInterrupt()
        r = self.run_dummy(send=interrupt)
        self.assertTrue(r['reason'].startswith('ORCHESTRATOR_INTERRUPTED_'))
        self.assertEqual(len(r['incomplete']), 2)
        self.assertTrue((self.root / 'SYNTHETIC_0_A/STARTED.json').exists())
        verify_manifest(self.root)

    def test_live_without_clearance_never_constructs_sdk(self):
        import orchestrator
        with patch.object(orchestrator, 'read', return_value={}), patch('google.genai.Client') as client:
            with self.assertRaises(PermissionError): orchestrator.live('unused', 'unused')
            client.assert_not_called()

    def test_nonfinite_budget_fails_closed(self):
        with self.assertRaises(PermissionError): self.run_dummy(budget=float('nan'))
        self.assertEqual(self.calls, [])

    def test_sdk_transport_mock_exact_configuration(self):
        from orchestrator import send_gemini
        req = amended_request(make_request(fixture(), 'A'))
        with patch('google.genai.Client') as factory, patch('orchestrator.os.getenv', return_value='DUMMY_NOT_A_CREDENTIAL'):
            client = factory.return_value
            client.models.generate_content.return_value = dummy_response()
            result = send_gemini(req)
            options = factory.call_args.kwargs['http_options']
            self.assertEqual(options.timeout, 120000)
            self.assertEqual(options.retry_options.attempts, 1)
            args = client.models.generate_content.call_args.kwargs
            self.assertEqual(args['model'], MODEL)
            self.assertEqual(args['contents'], req['contents'])
            self.assertEqual(args['config'].model_dump(exclude_none=True), req['config'])
            client.models.generate_content.assert_called_once()
            client.close.assert_called_once()

    def test_sdk_transport_mock_failure_no_retry(self):
        from orchestrator import send_gemini
        req = amended_request(make_request(fixture(), 'B'))
        with patch('google.genai.Client') as factory, patch('orchestrator.os.getenv', return_value='DUMMY_NOT_A_CREDENTIAL'):
            client = factory.return_value
            client.models.generate_content.side_effect = TimeoutError()
            with self.assertRaises(TimeoutError): send_gemini(req)
            client.models.generate_content.assert_called_once()
            client.close.assert_called_once()


if __name__ == '__main__':
    unittest.main()
