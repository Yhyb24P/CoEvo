"""Actual Pi tool boundary checks, without a model or network access."""
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from coevo.sandbox import command, execute

PI_ENTRY = Path('.worktrees/momo-code/packages/opencode/node_modules/@earendil-works/pi-coding-agent/dist/index.js')
ENVIRONMENT = Path('.cache/task-env')


@unittest.skipUnless(shutil.which('bwrap') and (ENVIRONMENT / 'bin/python').exists(), 'Local task environment required')
class TaskBoundaryTests(unittest.TestCase):
    def test_shell_does_not_expose_host_project_and_timeout_is_recorded(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp) / 'workspace'
            workspace.mkdir()
            (workspace / 'input.txt').write_text('task input')
            check = "from pathlib import Path; assert Path('input.txt').read_text() == 'task input'; assert not Path('/home/yhshy/git_files/CoEvo').exists()"
            result = execute(workspace, ENVIRONMENT, ['python', '-c', check], Path(tmp) / 'check.log', readonly=True)
            self.assertEqual(result['exit_code'], 0)
            result = execute(workspace, ENVIRONMENT, ['python', '-c', 'import time; time.sleep(10)'], Path(tmp) / 'timeout.log', timeout=0.1)
            self.assertTrue(result['timed_out'])
            self.assertNotEqual(result['exit_code'], 0)

    @unittest.skipUnless(PI_ENTRY.exists() and shutil.which('node'), 'Pinned Pi SDK required')
    def test_actual_pi_tools_enforce_scope_and_budget(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace = root / 'workspace'
            workspace.mkdir()
            (workspace / 'input.txt').write_text('task input')
            (workspace / 'outside').symlink_to('/etc/passwd')
            probes = [
                {'name': 'read', 'arguments': {'path': '/workspace/input.txt'}},
                {'name': 'read', 'arguments': {'path': 'outside'}},
                {'name': 'write', 'arguments': {'path': '../escape', 'content': 'blocked'}},
                {'name': 'write', 'arguments': {'path': '/workspace/nested/output.txt', 'content': 'actual result'}},
                {'name': 'bash', 'arguments': {'command': 'cat nested/output.txt'}},
                {'name': 'write', 'arguments': {'path': 'over-budget', 'content': 'blocked'}},
            ]
            request = {'workspace': str(workspace), 'run_dir': str(root / 'run'),
                       'pi_entry': str(PI_ENTRY.resolve()), 'sandbox_prefix': command(workspace, ENVIRONMENT, []),
                       'tool_probe': probes, 'max_tool_calls': 5}
            path = root / 'request.json'
            path.write_text(json.dumps(request))
            subprocess.run(['node', 'scripts/pi-project-agent.mjs'],
                           env={**os.environ, 'COEVO_REQUEST_FILE': str(path)}, check=True, timeout=30,
                           capture_output=True, text=True)
            results = json.loads((root / 'run/tool-probe.json').read_text())
            for index in [1, 2, 5]:
                self.assertIn('error', results[index])
            self.assertIn('actual result', str(results[4]))
            self.assertFalse((root / 'escape').exists())
            self.assertFalse((workspace / 'over-budget').exists())
