import json
import tempfile
import unittest
from pathlib import Path
from coevo.note_revision import feedback_data
from coevo.context_trial import task_cases


class NoteRevisionTests(unittest.TestCase):
    def test_feedback_keeps_actual_failure_without_checker_answer(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);workspace=root/'evaluation/agent-note/filter-withdrawal/workspace';workspace.mkdir(parents=True)
            (workspace/'output.json').write_text('{"ids":["q"]}')
            (root/'panel.json').write_text(json.dumps([{'name':'filter-withdrawal','prompt':'Use selected, ids withdrawn','expected':{'output.json':'PRIVATE_CHECKER_ANSWER'}}]))
            (root/'summary.json').write_text(json.dumps({'rows':[{'mode':'agent-note','family':'filter','name':'filter-withdrawal','case_kind':'withdrawal','passed':False,'outputs':{'output.json':False}}]}))
            rows=feedback_data(root,'filter')
            self.assertEqual(rows[0]['actual_output']['output.json'],'{"ids":["q"]}')
            self.assertIn('selected',rows[0]['current_user_requirement'])
            self.assertNotIn('PRIVATE_CHECKER_ANSWER',json.dumps(rows))
            self.assertFalse(feedback_data(root,'hash'))

    def test_new_input_panel_has_same_interventions_but_no_exact_old_inputs(self):
        old={(f,k,json.dumps(s['inputs'],sort_keys=True)) for f,k,s in task_cases(404)}
        new={(f,k,json.dumps(s['inputs'],sort_keys=True)) for f,k,s in task_cases(505)}
        self.assertEqual(len(new),12);self.assertFalse(old&new)
        self.assertEqual({(f,k) for f,k,_ in old},{(f,k) for f,k,_ in new})
