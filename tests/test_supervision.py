import copy
import json
import tempfile
import unittest
from pathlib import Path
from coevo.everyday import prepare,verify
from coevo.behavior import certify
from coevo.supervision import project,admit,plan,output_target
from tests.test_everyday_behavior import fixture

class SupervisionTests(unittest.TestCase):
    def test_context_is_identical_and_only_verified_mask_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/'run';task=prepare(out,'normalize');fixture(task,out,fail_first=True)
            self.assertTrue(verify(task,out)['passed']);targets=certify(task,out)
            local=project(targets,'output-only');full=project(targets,'full')
            self.assertEqual(local['messages'],full['messages']);self.assertEqual(local['tools'],full['tools'])
            self.assertEqual(len(local['target_indices']),1);self.assertEqual(len(full['target_indices']),3)
            self.assertIs(admit(local),local);self.assertIs(admit(full),full)
            bad=copy.deepcopy(local);bad['target_indices']=full['target_indices']
            with self.assertRaises(ValueError):admit(bad)
            with self.assertRaises(ValueError):project([targets[0]],'output-only')

    def test_readonly_bash_is_not_output_supervision(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);p=root/'transcript.json';p.write_text('{}')
            c={'behavior_kind':'bash','raw_generation_and_tool_trace_ref':str(p),
                'target':{'tool_calls':[{'id':'b'}]}}
            state={'tool_call_id':'b','before_outputs':{'output.json':''},'after_outputs':{'output.json':''}}
            (root/'tool-states.jsonl').write_text(json.dumps(state)+'\n');self.assertFalse(output_target(c))
            state['after_outputs']['output.json']='correct'
            (root/'tool-states.jsonl').write_text(json.dumps(state)+'\n');self.assertTrue(output_target(c))

    def test_whole_source_schedules_match_tokens_and_report_different_steps(self):
        result=plan({'output-only':[229,44],'full':[284,73]},[87,77,77],1100,40,.03)
        totals=[r['supervised_tokens'] for r in result.values()]
        self.assertLessEqual(max(totals)-min(totals),33)
        for r in result.values():self.assertLessEqual(r['supervised_tokens'],1100)
        self.assertGreater(result['full-replay']['replay_passes'],0)
        with self.assertRaises(ValueError):plan({'output-only':[229,44],'full':[284,73]},[87,77,77],100,40,.03)
