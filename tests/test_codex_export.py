import json
import tempfile
import unittest
from pathlib import Path
from coevo.codex_export import export, visible, propose_shell_targets


class CodexExportTests(unittest.TestCase):
    def test_only_visible_content_and_no_instruction_promotion(self):
        for payload in [
            {'type': 'reasoning', 'summary': 'hidden'},
            {'type': 'message', 'role': 'developer', 'content': [{'type': 'input_text', 'text': 'rules'}]},
            {'type': 'message', 'role': 'assistant', 'channel': 'analysis', 'content': [{'type': 'output_text', 'text': 'hidden'}]},
            {'type': 'message', 'role': 'user', 'content': [{'type': 'input_text', 'text': '# AGENTS.md instructions for x'}]},
            {'type': 'function_call_output', 'call_id': 'c', 'output': 'api_key=abcdefghijklmnopqrstuvwxyz'},
            {'type': 'message', 'role': 'user', 'content': [{'type': 'input_text', 'text': '服务器密码为：synthetic-only-placeholder'}]},
            {'type': 'function_call', 'name': 'exec_command', 'arguments': '{"password":"synthetic-only-placeholder"}'},
        ]:
            self.assertIsNone(visible(payload)[0])
        record, reason = visible({'type': 'message', 'role': 'assistant', 'phase': 'final_answer',
                                  'content': [{'type': 'output_text', 'text': 'Visible result'}]})
        self.assertIsNone(reason)
        self.assertEqual(record['text'], 'Visible result')

    def test_source_isolation_partial_and_unmatched_calls(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'logs'
            root.mkdir()
            for i, workspace in enumerate(['/research', '/tables']):
                rows = [
                    {'type': 'session_meta', 'payload': {'id': 'repeated-id', 'cwd': workspace, 'base_instructions': 'DO NOT EXPORT'}},
                    {'type': 'response_item', 'payload': {'type': 'function_call', 'call_id': 'c', 'name': 'exec_command', 'arguments': '{}'}},
                    {'type': 'response_item', 'payload': {'type': 'message', 'role': 'assistant', 'content': [{'type': 'output_text', 'text': 'done'}]}},
                ]
                (root / f'rollout-{i}.jsonl').write_text('\n'.join(json.dumps(r) for r in rows) + '\n{"unfinished":')
            out = Path(tmp) / 'export'
            summary = export(root, out)
            manifest = json.loads((out / 'manifest.json').read_text())
            self.assertEqual(summary['sessions'], 2)
            self.assertEqual(summary['training_candidates'], 0)
            self.assertEqual(len({s['export'] for s in manifest['sessions']}), 2)
            self.assertEqual(len({s['isolation_group'] for s in manifest['sessions']}), 2)
            for s in manifest['sessions']:
                records = [json.loads(line) for line in (out / s['export']).read_text().splitlines()]
                self.assertFalse(records[0]['paired'])
                self.assertFalse(s['train_ready'])
                self.assertEqual(s['split'], 'unassigned')
                self.assertNotIn('DO NOT EXPORT', (out / s['export']).read_text())
            self.assertEqual(summary['excluded']['malformed_or_partial_line'], 2)

    def test_shell_proposals_are_not_admitted_training_targets(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'logs'
            root.mkdir()
            rows = [
                {'type': 'session_meta', 'payload': {'id': 'session', 'cwd': '/project'}},
                {'type': 'response_item', 'payload': {'type': 'message', 'role': 'user', 'content': [{'type': 'input_text', 'text': 'Inspect files'}]}},
                {'type': 'response_item', 'payload': {'type': 'function_call', 'call_id': 'c', 'name': 'exec_command', 'arguments': json.dumps({'cmd': 'ls /project', 'workdir': '/project'})}},
                {'type': 'response_item', 'payload': {'type': 'function_call_output', 'call_id': 'c', 'output': 'Process exited with code 0\nOutput: fixture'}},
            ]
            (root / 'rollout-1.jsonl').write_text('\n'.join(json.dumps(r) for r in rows))
            out = Path(tmp) / 'out'
            export(root, out)
            audit = propose_shell_targets(out)
            self.assertEqual(audit['shell_proposals'], 1)
            self.assertEqual(audit['training_candidates'], 0)
            proposal = json.loads((out / 'shell-proposals.jsonl').read_text())
            self.assertFalse(proposal['train_ready'])
            self.assertEqual(proposal['actor'], 'teacher_codex')
            self.assertEqual(json.loads(proposal['proposed_target']['tool_calls'][0]['function']['arguments']), {'command': 'ls /workspace'})
