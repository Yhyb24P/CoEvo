import copy
import json
import tempfile
import unittest
from pathlib import Path
from coevo.everyday import prepare,verify
from coevo.behavior import certify
from coevo.supervision import project,admit,plan,output_target,update_groups
from tests.test_everyday_behavior import fixture

class SupervisionTests(unittest.TestCase):
    def test_token_matching_can_keep_same_optimizer_update_count(self):
        from collections import Counter
        a=update_groups(12,3,6,0,3);b=update_groups(12,3,3,0,3);c=update_groups(12,3,3,1,3)
        self.assertEqual([len(x) for x in [a,b,c]],[36,36,36])
        self.assertEqual(Counter(i for g in a for i in g),Counter({i:6 for i in range(12)}))
        self.assertEqual(Counter(i for g in b for i in g),Counter({i:3 for i in range(12)}))
        self.assertEqual(Counter(i for g in c for i in g),Counter({**{i:3 for i in range(12)},12:1,13:1,14:1}))

    def test_same_family_traces_keep_distinct_dataset_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            projected=[]
            for index in range(2):
                out=Path(tmp)/str(index);task=prepare(out,'normalize')
                task['episode_id']=f'L-variant-{index}'
                fixture(task,out);self.assertTrue(verify(task,out)['passed'])
                projected.append(project(certify(task,out),'full'))
            self.assertEqual(projected[0]['source_cluster_id'],projected[1]['source_cluster_id'])
            self.assertNotEqual(projected[0]['candidate_id'],projected[1]['candidate_id'])

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
