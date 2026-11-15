"""Offline identity/idempotency tests. Never constructs an API client."""
import unittest
from collections import Counter

from continuation import calculate_pending, select_pending


class ContinuationTests(unittest.TestCase):
    def frame(self):
        return [{'case_id': f'CASE_{i:03}', 'arm': a} for i in range(102) for a in 'ABCD']

    def test_original_order_filtered_without_reordering(self):
        order = self.frame()
        attempted = [(x['case_id'], x['arm']) for x in order[:156]]
        missing = [{**x, 'status': 'NOT_DISPATCHED'} for x in order[156:]]
        self.assertEqual(select_pending(order, attempted, missing), order[156:])

    def test_attempted_failures_are_never_selected(self):
        order = self.frame()
        attempted = [(x['case_id'], x['arm']) for x in order[:156]]
        # Selection uses attempted identity, regardless of SUCCESS/TIMEOUT/TRUNCATED.
        missing = [{**x, 'status': 'NOT_DISPATCHED'} for x in order[156:]]
        missing[0] = {**order[2], 'status': 'NOT_DISPATCHED'}
        with self.assertRaisesRegex(ValueError, 'resubmitted'):
            select_pending(order, attempted, missing)

    def test_reordered_or_incomplete_ledger_is_rejected(self):
        order = self.frame()
        attempted = [(x['case_id'], x['arm']) for x in order[:156]]
        missing = [{**x, 'status': 'NOT_DISPATCHED'} for x in order[156:]]
        missing[0], missing[1] = missing[1], missing[0]
        with self.assertRaisesRegex(ValueError, 'order'):
            select_pending(order, attempted, missing)
        with self.assertRaises(ValueError):
            select_pending(order, attempted, missing[:-1])

    def test_only_explicit_never_dispatched_status(self):
        order = self.frame()
        attempted = [(x['case_id'], x['arm']) for x in order[:156]]
        missing = [{**x, 'status': 'NOT_DISPATCHED'} for x in order[156:]]
        missing[0]['status'] = 'INCOMPLETE_RESERVED'
        with self.assertRaisesRegex(ValueError, 'exclusively undispatched'):
            select_pending(order, attempted, missing)

    def test_real_sealed_partition_and_request_count(self):
        result = calculate_pending()
        self.assertEqual(result['pending_count'], 252)
        self.assertEqual(result['pending_api_calls'], 118)
        self.assertEqual(Counter(x['arm'] for x in result['entries']),
                         Counter(A=53, B=65, C=68, D=66))
        self.assertEqual(len({(x['case_id'], x['arm']) for x in result['entries']}), 252)
        self.assertTrue(all('request_sha256' in x for x in result['entries'] if x['arm'] in 'AB'))
        self.assertTrue(all('request_sha256' not in x for x in result['entries'] if x['arm'] in 'CD'))


if __name__ == '__main__':
    unittest.main()
