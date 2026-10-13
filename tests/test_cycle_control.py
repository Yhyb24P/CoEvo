import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from coevo.rsi import run
from coevo.state import State


class CycleControlTests(unittest.TestCase):
    def test_collected_data_waits_for_user_training_and_keeps_accepted_model(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = State(str(Path(tmp) / "state.sqlite"))
            state.decide("previous", "old-adapter", None, True, {})
            state.save_cycle(1, "collected", {"cycle": 1, "parent": state.accepted(),
                "collection": {"candidate_count": 2, "dataset": "authorized-candidates.jsonl"}})
            with patch("coevo.rsi.State", return_value=state), \
                 patch("coevo.rsi.read_config", return_value={}), \
                 patch("coevo.rsi.subprocess.run", side_effect=AssertionError("Training must not execute")), \
                 patch("coevo.rsi.Server", side_effect=AssertionError("No server needed for handoff")):
                result = run("unused-config", tmp, cycles=3)
            self.assertEqual(result["status"], "awaiting_user_training")
            self.assertFalse(result["training_executed"])
            self.assertEqual(state.cycle(1)["phase"], "awaiting_user_training")
            self.assertEqual(state.accepted()["adapter"], "old-adapter")


if __name__ == "__main__":
    unittest.main()
