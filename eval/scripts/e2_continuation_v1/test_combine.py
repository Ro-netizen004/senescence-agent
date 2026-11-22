"""Offline synthetic checks of merger arithmetic, audit sampling and E4 blinding."""
import json
import tempfile
import unittest
from pathlib import Path

from combine import e4_package, fixed_audit_sample, four_arm_complete
from common import OUT, read


class CombinedAnalysisTests(unittest.TestCase):
    def test_four_arm_completeness_excludes_failure(self):
        frame = [{'case_id': 'CASE_ONE', 'family': 'F3'},
                 {'case_id': 'CASE_TWO', 'family': 'F3'}]
        scores = []
        for case in frame:
            for arm in 'ABCD':
                scores.append({'case_id': case['case_id'], 'family': 'F3', 'arm': arm,
                               'status': 'API_FAILURE' if case['case_id'] == 'CASE_TWO' and arm == 'B' else 'SUCCESS',
                               'unsupported_screen_event': arm == 'D',
                               'opportunities': 2, 'retained': int(arm == 'C')})
        row = next(x for x in four_arm_complete(scores, frame) if x['family'] == 'F3')
        self.assertEqual(row['complete_four_arm_contexts'], 1)
        self.assertEqual(row['incomplete_four_arm_contexts'], 1)
        self.assertEqual(row['arms']['D']['provisional_events'], 1)
        self.assertEqual(row['arms']['C']['retained'], 1)

    def test_audit_sample_is_fixed_hash_selection(self):
        scores = [{'case_id': f'CASE_{i}', 'arm': 'D', 'status': 'SUCCESS',
                   'screen_flags': [{'category': 'artifact_origin_candidate'}]} for i in range(20)]
        scores += [{'case_id': 'NOT_FLAGGED', 'arm': 'D', 'status': 'SUCCESS', 'screen_flags': []},
                   {'case_id': 'WRONG_ARM', 'arm': 'A', 'status': 'SUCCESS',
                    'screen_flags': [{'category': 'artifact_origin_candidate'}]}]
        a = fixed_audit_sample(scores)
        self.assertEqual(a, fixed_audit_sample(list(reversed(scores))))
        self.assertEqual(a['eligible_flags'], 20)
        self.assertEqual(len(a['selected_case_ids']), 12)
        self.assertNotIn('WRONG_ARM', a['selected_case_ids'])

    def test_e4_package_has_frozen_40_contexts_and_no_arm_labels(self):
        sample = read(OUT / 'E2_E4_SAMPLE.json')['contexts']
        records = [{'case_id': c, 'arm': a, 'status': 'SUCCESS',
                    'text': '[System] inference_state=TEST\nSynthetic output only.',
                    'source_attempt': 'SYNTHETIC'} for c in sample for a in 'ABCD']
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'e4'
            private = e4_package(records, path)
            index = json.loads((path / 'INDEX.json').read_text())
            self.assertEqual(len(index), 160)
            self.assertEqual(len(private), 160)
            self.assertEqual(len({x['context_id'] for x in index}), 40)
            self.assertTrue(all('arm' not in x and 'case_id' not in x for x in index))
            self.assertTrue(all('inference_state=' not in (path / f"{x['response_id']}.txt").read_text() for x in index))
            self.assertTrue(all('case_id' not in json.loads((path / f'CONTEXT_{i:03}.json').read_text())['case_id']
                                for i in range(1, 41)))


if __name__ == '__main__':
    unittest.main()
