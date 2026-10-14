import copy
import tempfile
import unittest
from pathlib import Path
from coevo.everyday import prepare, verify
from coevo.behavior import certify
from coevo.sequences import compose, admit
from tests.test_everyday_behavior import fixture


class SequenceTests(unittest.TestCase):
    def test_failed_context_is_retained_but_only_verified_turns_are_targets(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/'run';task=prepare(out,'normalize')
            fixture(task,out,fail_first=True)
            self.assertTrue(verify(task,out)['passed'])
            targets=certify(task,out)
            sequence=compose(targets)
            self.assertIs(admit(sequence),sequence)
            self.assertEqual([targets[i]['behavior_kind'] for i in range(len(targets))],['read','write','stop'])
            failed=[i for i,m in enumerate(sequence['messages']) if any(c['id']=='bad' for c in m.get('tool_calls',[]))]
            self.assertEqual(len(failed),1)
            self.assertNotIn(failed[0],sequence['target_indices'])
            self.assertTrue(any(m['role']=='tool' and m.get('tool_call_id')=='bad' for m in sequence['messages']))
            mutated=copy.deepcopy(sequence);mutated['messages'][-1]['content']='false statement'
            with self.assertRaises(ValueError):admit(mutated)
            altered=copy.deepcopy(targets);altered[-1]['source_cluster_id']='another-source'
            with self.assertRaises(ValueError):compose(altered)
