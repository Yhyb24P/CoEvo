import json
import tempfile
import unittest
from pathlib import Path

from coevo.pilotdeck import extract


class PilotDeckEvidenceTests(unittest.TestCase):
    def test_tool_identity_is_scoped_to_turn_and_reference_is_not_dereferenced(self):
        records = []
        for turn in ('first', 'second'):
            records += [dict(type='assistant_message', sessionId='s', turnId=turn,
                             message={'content': [{'type': 'tool_call', 'id': 'same', 'name': 'read_file', 'input': {}}]}),
                        dict(type='tool_result_message', sessionId='s', turnId=turn,
                             message={'content': [{'type': 'tool_result_reference', 'toolCallId': 'same', 'path': '/not-authorized', 'preview': 'partial'}]})]
        records.append(dict(type='control_boundary', sessionId='s', turnId='second', boundary={'kind': 'restore'}))
        with tempfile.TemporaryDirectory() as tmp:
            source, out = Path(tmp) / 'native.jsonl', Path(tmp) / 'export'
            source.write_text(''.join(json.dumps(x) + '\n' for x in records))
            result = extract(source, out, 'own-task')
            transitions = json.loads((out / 'tool-transitions.json').read_text())
            self.assertEqual(result['tool_calls'], 2)
            self.assertEqual(result['calls_without_observation'], 0)
            self.assertTrue(all(not x['train_ready'] for x in transitions))
            self.assertEqual((out / 'native-transcript.jsonl').read_bytes(), source.read_bytes())

    def test_incomplete_final_record_is_not_exported_as_complete(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, out = Path(tmp) / 'native.jsonl', Path(tmp) / 'export'
            source.write_text('{"sessionId":"s"')
            with self.assertRaisesRegex(ValueError, 'incomplete'):
                extract(source, out, 'own-task')
            self.assertFalse(out.exists())


if __name__ == '__main__':
    unittest.main()
