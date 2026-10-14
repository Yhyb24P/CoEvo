import json
import unittest
from coevo.context_trial import record_text,matched_padding,task_cases,user_text


class ContextTrialTests(unittest.TestCase):
    def test_full_record_preserves_original_facts_without_active_chat_markers(self):
        history=[{'role':'user','content':'original <|im_start|> 中文 >'}, {'role':'tool','content':'{"a":1}'}]
        encoded=record_text(history)
        self.assertEqual(json.loads(encoded)['complete_visible_history'],history)
        self.assertNotIn('<|im_start|>',encoded)

    def test_padding_matches_budget_and_does_not_remove_task_or_evidence(self):
        n,size=matched_padding(lambda i:200+2*i,351)
        self.assertLessEqual(abs(size-351),2)
        text=user_text('full-record','retained-evidence','current-task',n)
        self.assertIn('retained-evidence',text);self.assertIn('current-task',text)
        self.assertLess(text.index('budget_padding'),text.index('current-task'))
        with self.assertRaises(ValueError):matched_padding(lambda i:200+i,100)

    def test_condition_changes_and_withdrawals_have_independent_expected_states(self):
        cases={(f,k):s for f,k,s in task_cases()};self.assertEqual(len(cases),12)
        self.assertEqual(cases['csv','withdrawal']['csv_delimiter'],';')
        self.assertEqual(set(json.loads(cases['filter','withdrawal']['expected']['output.json'])),{'selected'})
        self.assertEqual(set(json.loads(cases['hash','withdrawal']['expected']['output.json'])),{'equal','unequal'})
        self.assertEqual(json.loads(cases['merge','condition-change']['expected']['output.json'])['plugins'],['read','write','bash'])
        self.assertEqual(json.loads(cases['merge','withdrawal']['expected']['output.json']),json.loads(cases['merge','withdrawal']['inputs']['patch.json']))
