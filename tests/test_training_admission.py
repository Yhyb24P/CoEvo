import json
import tempfile
import unittest
from pathlib import Path
from coevo.train import admit
from coevo.state import State


class AdmissionTests(unittest.TestCase):
    def candidate(self, root):
        evidence = Path(root) / 'verdict.json'
        evidence.write_text(json.dumps({'passed': True, 'post_state_hash': 'verified-state', 'actual': {'result': 3}}))
        return {'split': 'L', 'train_authorized': True, 'verifier_ref': str(evidence),
                'verified_state_hash': 'verified-state', 'target': {'role': 'assistant', 'tool_calls': [
                    {'function': {'name': 'write', 'arguments': json.dumps({'path': 'output.json', 'content': '{"result":3}'})}}]}}

    def test_only_verified_learning_source_is_admitted(self):
        with tempfile.TemporaryDirectory() as root:
            candidate = self.candidate(root)
            self.assertIs(admit(candidate), candidate)
            with self.assertRaises(ValueError):
                admit({**candidate, 'split': 'H'})
            with self.assertRaises(ValueError):
                admit({**candidate, 'train_authorized': False})

    def test_episode_success_does_not_authorize_wrong_action(self):
        with tempfile.TemporaryDirectory() as root:
            candidate = self.candidate(root)
            candidate['target']['tool_calls'][0]['function']['arguments'] = '{"content":"{\\"result\\":4}"}'
            with self.assertRaises(ValueError):
                admit(candidate)

    def test_rejected_adapter_preserves_accepted_version(self):
        with tempfile.TemporaryDirectory() as root:
            state = State(str(Path(root) / 'state.sqlite'))
            state.decide('v1', 'adapter-1', None, True, {'real': 'test-fixture'})
            state.decide('v2', 'adapter-2', 'v1', False, {'real': 'test-fixture'})
            self.assertEqual(state.accepted()['version'], 'v1')
            state.save_cycle(2, 'trained', {'adapter': 'adapter-2'})
            reopened = State(str(Path(root) / 'state.sqlite'))
            self.assertEqual(reopened.cycle(2)['phase'], 'trained')
            self.assertEqual(reopened.accepted()['adapter'], 'adapter-1')


if __name__ == '__main__':
    unittest.main()
