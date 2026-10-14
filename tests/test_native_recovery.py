"""Actual pinned SDK branching and task tools; no model capability claims."""
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from coevo.sandbox import command
from tests.test_project_tools import PI_ENTRY, ENVIRONMENT


@unittest.skipUnless(PI_ENTRY.exists() and shutil.which('node') and (ENVIRONMENT / 'bin/python').exists(), 'Local pinned Pi and task environment required')
class NativeRecoveryTests(unittest.TestCase):
    def execute(self, root, request):
        p = root / 'request.json'
        p.write_text(json.dumps(request))
        return subprocess.run(['node', 'scripts/pi-project-agent.mjs'],
                              env={**os.environ, 'COEVO_REQUEST_FILE': str(p)},
                              capture_output=True, text=True, timeout=25)

    def test_sdk_checkpoint_keeps_exact_prefix_and_excludes_later_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); ws = root / 'workspace'; ws.mkdir()
            source = """
            import {pathToFileURL} from 'node:url';
            const {SessionManager} = await import(pathToFileURL(process.argv[2]));
            const m = SessionManager.create(process.argv[1] + '/workspace', process.argv[1] + '/source');
            const assistant = text => ({role:'assistant',content:[{type:'text',text}],api:'openai-completions',
              provider:'coevo-local',model:'fixture',stopReason:'stop',timestamp:1,
              usage:{input:1,output:1,cacheRead:0,cacheWrite:0,cost:{input:0,output:0,cacheRead:0,cacheWrite:0,total:0}}});
            m.appendMessage({role:'user',content:'ORIGINAL TASK',timestamp:1});
            const checkpoint = m.appendMessage(assistant('EARLY FAILURE'));
            m.appendMessage({role:'user',content:'EXCLUDED LATE HISTORY',timestamp:2});
            m.appendMessage(assistant('EXCLUDED LATE ANSWER'));
            console.log(JSON.stringify({file:m.getSessionFile(),checkpoint}));
            """
            proc = subprocess.run(['node', '--input-type=module', '-e', source, str(root), str(PI_ENTRY.resolve())], check=True, capture_output=True, text=True)
            selected = json.loads(proc.stdout)
            source_file = Path(selected['file']); before = source_file.read_bytes()
            request = {'workspace': str(ws), 'run_dir': str(root / 'run'), 'pi_entry': str(PI_ENTRY.resolve()),
                       'resume_file': str(source_file), 'resume_entry_id': selected['checkpoint'],
                       'endpoint': 'http://127.0.0.1:1/v1', 'model': 'fixture', 'context_tokens': 4096,
                       'prompts': ['EXTERNAL FEEDBACK'], 'system_prompt': 'Transport fixture.',
                       'timeout_ms': 15000, 'max_tool_calls': 1, 'sandbox_prefix': ['unused'], 'preview_only': True}
            result = self.execute(root, request)
            self.assertNotEqual(result.returncode, 0)
            provenance = json.loads((root / 'run/checkpoint-provenance.json').read_text())
            self.assertTrue(provenance['native_prefix_equal'])
            self.assertTrue(provenance['source_unchanged'])
            self.assertEqual(before, source_file.read_bytes())
            payload = (root / 'run/payloads.jsonl').read_text()
            self.assertIn('EARLY FAILURE', payload)
            self.assertIn('EXTERNAL FEEDBACK', payload)
            self.assertNotIn('EXCLUDED LATE', payload)

    def test_four_unchanged_failed_commands_stop_before_another_tool(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); ws = root / 'workspace'; ws.mkdir()
            request = {'workspace': str(ws), 'run_dir': str(root / 'run'), 'pi_entry': str(PI_ENTRY.resolve()),
                       'max_tool_calls': 10, 'repeat_failure_limit': 4, 'sandbox_prefix': command(ws, ENVIRONMENT, []),
                       'tool_probe': [{'name': 'bash', 'arguments': {'command': 'exit 1'}}] * 4 +
                                     [{'name': 'write', 'arguments': {'path': 'must-not-exist', 'content': 'bad'}}]}
            self.assertEqual(self.execute(root, request).returncode, 0)
            stop = json.loads((root / 'run/resource-stop.json').read_text())
            self.assertEqual(stop['consecutive'], 4)
            guards = [json.loads(l) for l in (root / 'run/failure-guard.jsonl').read_text().splitlines()]
            self.assertEqual([g['repeated_failures'] for g in guards], [1, 2, 3, 4])
            self.assertFalse((ws / 'must-not-exist').exists())

    def test_failed_command_with_real_state_progress_does_not_trip_guard(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); ws = root / 'workspace'; ws.mkdir()
            cmd = 'python -c "from pathlib import Path; p=Path(\'progress\'); p.write_text(str(int(p.read_text())+1 if p.exists() else 1)); raise SystemExit(1)"'
            request = {'workspace': str(ws), 'run_dir': str(root / 'run'), 'pi_entry': str(PI_ENTRY.resolve()),
                       'max_tool_calls': 10, 'repeat_failure_limit': 4, 'sandbox_prefix': command(ws, ENVIRONMENT, []),
                       'tool_probe': [{'name': 'bash', 'arguments': {'command': cmd}}] * 4}
            self.assertEqual(self.execute(root, request).returncode, 0)
            self.assertEqual((ws / 'progress').read_text(), '4')
            self.assertFalse((root / 'run/resource-stop.json').exists())
