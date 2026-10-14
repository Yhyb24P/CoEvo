import tempfile
import unittest
from pathlib import Path
from coevo.state import State
from coevo.memory import Memory


class MemoryTests(unittest.TestCase):
    def test_condition_and_ancestor_revocation_are_separate_interventions(self):
        with tempfile.TemporaryDirectory() as tmp:
            c={'study_id':'memory','stream_id':'test','arm_id':'A','state_path':str(Path(tmp)/'db.sqlite')}
            state=State.for_experiment(c);memory=Memory(state)
            memory.register('instance','instance','L-origin','real instance',{'operation':'unique'},['fixture-verdict'])
            memory.register('skill','skill','L-origin','conditional procedure',{'operation':'unique'},['fixture-verdict'],['instance'])
            self.assertEqual(memory.retrieve({'operation':'sort'},'M1')['selected_ids'],['instance'])
            self.assertEqual(memory.retrieve({'operation':'sort'},'M2')['selected_ids'],[])
            self.assertEqual(memory.retrieve({'operation':'unique'},'M2')['selected_ids'],['skill'])
            memory.revoke('instance','fixture revocation')
            self.assertEqual(memory.retrieve({'operation':'unique'},'M2')['selected_ids'],['skill'])
            self.assertEqual(memory.retrieve({'operation':'unique'},'M3')['selected_ids'],[])
            state.close();state=State.for_experiment(c);memory=Memory(state)
            self.assertEqual(memory.retrieve({'operation':'unique'},'M3')['selected_ids'],[])
            with self.assertRaises(ValueError):memory.register('instruction','Instruction','source','authority',{},['fixture'])
            with self.assertRaises(ValueError):memory.register('bad','skill','another-source','x',{},['fixture'],['instance'])
            state.close()
