import unittest
from collections import Counter
from coevo.selector_trial import stratified_random,matched_schedules


class SelectorTrialTests(unittest.TestCase):
    def test_stratified_random_uses_feasible_whole_sources_and_reproducible_seed(self):
        options=[{'family':f,'supervised_tokens':cost} for f,cost in [('csv',1090),('csv',335),('hash',435),('hash',190),('filter',175),('merge',146)]]
        a=stratified_random(options,1000,17)
        self.assertEqual(a,stratified_random(options,1000,17))
        self.assertEqual({options[i]['family'] for i in a},{'csv','hash','filter','merge'})
        self.assertLessEqual(sum(options[i]['supervised_tokens'] for i in a),1000)
        with self.assertRaises(ValueError):stratified_random(options,100,17)

    def test_common_budget_keeps_original_references_all_selected_sources_and_equal_updates(self):
        costs=[335,435,175,146]
        choices={'SF':[0,2],'SU-proxy':[1,2,3],'SR':[0,1,2,3]}
        p=matched_schedules(costs,choices)
        self.assertEqual(p,matched_schedules(costs,choices))
        for name,r in p['arms'].items():
            self.assertEqual(set(r['schedule']),set(choices[name]))
            self.assertEqual(r['supervised_tokens'],sum(costs[i] for i in r['schedule']))
            self.assertGreaterEqual(r['supervised_tokens'],p['budget']*.97)
            self.assertLessEqual(r['supervised_tokens'],p['budget'])
            self.assertEqual(len(r['update_groups']),12)
            self.assertTrue(all(r['update_groups']))
            self.assertEqual(Counter(r['schedule']),Counter(i for g in r['update_groups'] for i in g))

    def test_abstention_duplicate_and_impossible_budget_are_not_filled_in(self):
        for selection in [[],[0,0],[4]]:
            with self.assertRaises(ValueError):matched_schedules([100],{'SF':selection})
        with self.assertRaises(ValueError):matched_schedules([1000],{'SF':[0]},max_budget=500)
