import csv
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from coevo.mcm_run import forecast_check, termination
from coevo.sandbox import command
from tests.test_project_tools import PI_ENTRY


class ForecastTests(unittest.TestCase):
    def test_empty_length_limited_turn_is_not_normal_completion(self):
        t = {'messages': [{'role': 'assistant', 'stopReason': 'length'}], 'aborted': False, 'final_text': None}
        self.assertFalse(termination(t)['normal_stop'])
        self.assertFalse(termination(t)['final_response_present'])

    def test_invalid_numeric_forecasts_are_not_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'forecast.csv'
            p.write_text('NOC,Gold,Total,Gold_lower,Gold_upper,Total_lower,Total_upper\nX,nan,2,0,3,0,4\n')
            self.assertFalse(forecast_check(p)['valid'])
            p.write_text('NOC,Gold,Total,Gold_lower,Gold_upper,Total_lower,Total_upper\nX,1,2,0,3,0,4\n')
            self.assertTrue(forecast_check(p)['valid'])


@unittest.skipUnless(PI_ENTRY.exists() and Path('.cache/task-env/bin/python').exists(), 'Local Pi/environment required')
class InputBoundaryTests(unittest.TestCase):
    def test_readonly_data_blocks_direct_write_and_shell_but_allows_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); ws = root / 'workspace'; (ws / 'data').mkdir(parents=True)
            (ws / 'data/input.csv').write_text('immutable\n')
            request = {'workspace': str(ws), 'run_dir': str(root / 'run'), 'pi_entry': str(PI_ENTRY.resolve()),
                       'readonly_paths': ['data'], 'max_tool_calls': 5,
                       'sandbox_prefix': command(ws, '.cache/task-env', [], readonly_paths=['data']),
                       'tool_probe': [{'name': 'write', 'arguments': {'path': 'data/input.csv', 'content': 'bad'}},
                                      {'name': 'bash', 'arguments': {'command': 'echo bad > data/input.csv'}},
                                      {'name': 'write', 'arguments': {'path': 'result.txt', 'content': 'ok'}}]}
            p = root / 'request.json'; p.write_text(json.dumps(request))
            subprocess.run(['node', 'scripts/pi-project-agent.mjs'], env={**os.environ, 'COEVO_REQUEST_FILE': str(p)}, check=True, capture_output=True, timeout=20)
            results = json.loads((root / 'run/tool-probe.json').read_text())
            self.assertIn('Readonly', results[0]['error'])
            self.assertEqual((ws / 'data/input.csv').read_text(), 'immutable\n')
            self.assertEqual((ws / 'result.txt').read_text(), 'ok')
