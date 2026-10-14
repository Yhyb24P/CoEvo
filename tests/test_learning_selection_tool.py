import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

@unittest.skipUnless(shutil.which('node'),'Node required')
class SelectionToolTests(unittest.TestCase):
    def test_actual_tool_budget_reference_rejection_and_withdrawal(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger=Path(tmp)/'ledger.jsonl'
            script="""import {makeLearningSelectionTool} from './scripts/learning-selection.mjs';
const tool=makeLearningSelectionTool([{candidate_id:'correct-output',supervised_tokens:90},{candidate_id:'verified-stop',supervised_tokens:3}],90,process.argv[1],2);
for(const indices of [[1],[1,2],[3],[2,2],[]]) await tool.execute('case',{indices});
"""
            subprocess.run(['node','--input-type=module','-e',script,str(ledger)],check=True,capture_output=True,text=True)
            rows=[json.loads(x) for x in ledger.read_text().splitlines()]
            self.assertEqual([r['accepted'] for r in rows],[True,False,False,False,True])
            self.assertEqual(rows[0]['selected_ids'],['correct-output'])
            self.assertEqual(rows[-1]['selected_ids'],[])
