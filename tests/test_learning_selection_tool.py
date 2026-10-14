import json
import shutil
import subprocess
import tempfile
import unittest
import os
from pathlib import Path

@unittest.skipUnless(shutil.which('node'),'Node required')
class SelectionToolTests(unittest.TestCase):
    def test_inspecting_twelve_candidates_still_allows_nomination_with_declared_capacity(self):
        from tests.test_project_tools import PI_ENTRY
        if not PI_ENTRY.exists():self.skipTest('Pinned Pi SDK required; no model or download')
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);workspace=root/'workspace';workspace.mkdir();(workspace/'candidate.json').write_text('{}')
            for cap in [12,16]:
                run=root/str(cap)
                probes=[{'name':'read','arguments':{'path':'candidate.json'}}]*12
                probes.append({'name':'nominate_training','arguments':{'indices':[1]}})
                request={'workspace':str(workspace),'run_dir':str(run),'pi_entry':str(PI_ENTRY.resolve()),
                    'sandbox_prefix':['unused'],'allowed_write_paths':[],'max_tool_calls':cap,'tool_probe':probes,
                    'learning_candidates':[{'candidate_id':'verified-L','supervised_tokens':175}],
                    'training_selection_token_budget':1500,'training_selection_max_items':6}
                path=root/f'{cap}.json';path.write_text(json.dumps(request))
                subprocess.run(['node','scripts/pi-project-agent.mjs'],env={**os.environ,'COEVO_REQUEST_FILE':str(path)},
                    check=True,capture_output=True,text=True,timeout=30)
                result=json.loads((run/'tool-probe.json').read_text())[-1]
                if cap==12:
                    self.assertIn('budget',result['error']);self.assertFalse((run/'learning-selection.jsonl').exists())
                else:
                    self.assertTrue(result['result']['details']['accepted'])
                    self.assertTrue((run/'learning-selection.jsonl').exists())

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
