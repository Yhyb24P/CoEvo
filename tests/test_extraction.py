import json
import tempfile
import unittest
from pathlib import Path
from coevo.extract import extract, normalize


class ExtractionTests(unittest.TestCase):
    def test_thinking_and_tool_result_preserve_message_order(self):
        result = normalize([
            {"role": "user", "content": "read the input"},
            {"role": "assistant", "content": [
                {"type": "thinking", "thinking": "Need the actual file."},
                {"type": "toolCall", "id": "call-1", "name": "read", "arguments": {"path": "input.json"}}]},
            {"role": "toolResult", "toolCallId": "call-1", "content": [{"type": "text", "text": "input"}]}])
        self.assertEqual(result["visible_thinking"][0]["text"], "Need the actual file.")
        self.assertEqual(result["tool_calls"][0]["result"]["message_index"], 2)
        self.assertEqual(result["user_inputs"][0]["message_index"], 0)

    def test_interrupted_unlabelled_trace_is_exported_without_training_candidate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "input"
            root.mkdir()
            event = {"type": "message_end", "message": {"role": "assistant", "content": "partial reply"}}
            (root / "events.jsonl").write_text(json.dumps(event)+"\n{unfinished")
            summary = extract(root, Path(tmp) / "out")
            self.assertFalse(summary["training_executed"])
            self.assertEqual(summary["verified_candidate_count"], 0)
            self.assertEqual(summary["incomplete_records"], 1)
            record = json.loads((Path(tmp)/"out/interactions.jsonl").read_text())
            self.assertFalse(record["train_authorized"])
            self.assertEqual(record["raw_messages"][0]["content"], "partial reply")

    def test_development_task_preserves_actor_and_feedback_without_training(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'input'
            root.mkdir()
            (root / 'task.json').write_text(json.dumps({
                'interaction_origin': 'researcher-task', 'actor': 'student', 'prompt_actor': 'researcher',
                'teacher_assisted': False, 'split': 'D', 'train_authorized': False,
                'source_cluster_id': 'cli-encoding', 'program_family': 'cli-file-encoding'}))
            (root / 'transcript.json').write_text(json.dumps({'system': 'test-fixture', 'tools': [],
                'messages': [{'role': 'assistant', 'content': 'Completion claim'}]}))
            (root / 'verdict.json').write_text(json.dumps({'passed': False, 'feedback_origin': 'external-executable-checks'}))
            result = extract(root, Path(tmp) / 'output', origin='user-interaction')
            record = json.loads((Path(tmp) / 'output/interactions.jsonl').read_text())
            self.assertEqual(record['interaction_origin'], 'researcher-task')
            self.assertEqual(record['prompt_actor'], 'researcher')
            self.assertEqual(record['feedback_origin'], 'external-executable-checks')
            self.assertFalse(record['teacher_assisted'])
            self.assertEqual(result['verified_candidate_count'], 0)


if __name__ == "__main__":
    unittest.main()
