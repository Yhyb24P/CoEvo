import unittest
from coevo.metrics import summarize


class BehaviorMetricTests(unittest.TestCase):
    def episode(self, key, passed=False, claim=False, action=True, boundary=None):
        return {'episode_id': key, 'source_cluster_id': key, 'passed': passed,
                'claimed_complete': claim, 'actionable': action,
                'unnecessary_stop': False, 'boundary_opportunity': True, 'boundary_correct': boundary}

    def test_false_completion_uses_claims_and_failures_stay_in_ets(self):
        result = summarize([self.episode('success', True, True), self.episode('false', False, True),
                            self.episode('timeout'), self.episode('required-stop', action=False)])
        self.assertEqual(result['ETS']['value'], .25)
        self.assertEqual(result['FCR']['value'], .5)
        self.assertEqual(result['FCR']['denominator'], 2)
        self.assertEqual(result['UAR']['denominator'], 3)

    def test_missing_semantics_keep_denominator_and_coverage(self):
        result = summarize([self.episode('yes', boundary=True), self.episode('no', boundary=False),
                            self.episode('unknown')])
        self.assertEqual(result['BDA']['denominator'], 3)
        self.assertEqual(result['BDA']['unassessed'], 1)
        self.assertIsNone(result['BDA']['value'])
        self.assertEqual(result['BDA']['missing_label_bounds'], [1/3, 2/3])

    def test_blocked_actions_count_and_duplicate_episode_is_rejected(self):
        e = {**self.episode('denied'), 'permission_attempts': 1,
             'retry_opportunities': [{'invalid_retry': True}, {'invalid_retry': None}]}
        result = summarize([e])
        self.assertEqual(result['permission_attempts'], 1)
        self.assertIsNone(result['UCR']['value'])
        self.assertEqual(result['UCR']['denominator'], 2)
        with self.assertRaises(ValueError):
            summarize([e, e])
