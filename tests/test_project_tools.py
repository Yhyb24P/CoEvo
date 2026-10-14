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
    @unittest.skipUnless(PI_ENTRY.exists() and shutil.which('node'), 'Pinned Pi SDK required')
    def test_file_and_terminal_tools_share_explicit_write_permissions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace = root / 'workspace'
            workspace.mkdir()
            (workspace / 'input.txt').write_text('protected')
            (workspace / 'output.txt').write_text('')
            (workspace / 'dangling').symlink_to(root / 'escaped')
            request = {'workspace': str(workspace), 'run_dir': str(root / 'run'),
                       'pi_entry': str(PI_ENTRY.resolve()), 'max_tool_calls': 6,
                       'allowed_write_paths': ['output.txt', 'dangling'],
                       'sandbox_prefix': command(workspace, ENVIRONMENT, [], readonly=True, writable_paths=['output.txt']),
                       'tool_probe': [
                           {'name': 'write', 'arguments': {'path': 'input.txt', 'content': 'forbidden'}},
                           {'name': 'write', 'arguments': {'path': 'dangling', 'content': 'forbidden'}},
                           {'name': 'write', 'arguments': {'path': 'output.txt', 'content': 'allowed'}},
                           {'name': 'write', 'arguments': {'path': '/workspace/output.txt', 'content': 'virtual-output-allowed'}},
                           {'name': 'bash', 'arguments': {'command': 'echo forbidden > input.txt'}},
                           {'name': 'bash', 'arguments': {'command': 'echo terminal-result > output.txt'}},
                       ]}
            path = root / 'request.json'
            path.write_text(json.dumps(request))
            subprocess.run(['node', 'scripts/pi-project-agent.mjs'], env={**os.environ, 'COEVO_REQUEST_FILE': str(path)},
                           check=True, timeout=30, capture_output=True, text=True)
            results = json.loads((root / 'run/tool-probe.json').read_text())
            self.assertIn('error', results[0])
            self.assertIn('error', results[1])
            self.assertNotIn('error', results[3])
            self.assertTrue(results[4]['result']['isError'])
            self.assertEqual((workspace / 'input.txt').read_text(), 'protected')
            self.assertEqual((workspace / 'output.txt').read_text(), 'terminal-result\n')
            self.assertFalse((root / 'escaped').exists())
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
