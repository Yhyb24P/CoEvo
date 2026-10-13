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


if __name__ == "__main__":
    unittest.main()
