import tempfile
import unittest
from pathlib import Path
from coevo.state import State


class ExperimentStateTests(unittest.TestCase):
    def config(self, root, stream='one', arm='A'):
        return {'study_id': 'pilot', 'stream_id': stream, 'arm_id': arm,
                'state_path': str(Path(root) / '{study_id}' / '{stream_id}' / '{arm_id}.sqlite')}

    def test_flows_arms_versions_and_experience_are_isolated(self):
        with tempfile.TemporaryDirectory() as root:
            config = self.config(root)
            state = State.for_experiment(config)
            state.decide('cycle-1', 'adapter-A', None, True, {'fixture': True})
            state.save_cycle(1, 'finished', {})
            state.add_experience({'candidate_id': 'source-1', 'source_cluster_id': 'source', 'verifier_ref': 'fixture'})
            state.close()
            for other in [self.config(root, stream='two'), self.config(root, arm='B')]:
                other_state = State.for_experiment(other)
                self.assertIsNone(other_state.accepted())
                self.assertIsNone(other_state.cycle(1))
                self.assertEqual(other_state.experience_context(), '')
                other_state.close()
            reopened = State.for_experiment(config)
            self.assertEqual(reopened.accepted()['adapter'], 'adapter-A')
            self.assertEqual(reopened.cycle(1)['phase'], 'finished')
            self.assertIn('source-1', reopened.experience_context())
            reopened.close()

    def test_same_database_cannot_be_rebound_or_adopt_old_state(self):
        with tempfile.TemporaryDirectory() as root:
            config = {**self.config(root), 'state_path': str(Path(root) / 'explicit.sqlite')}
            state = State.for_experiment(config)
            state.decide('v1', 'adapter-A', None, True, {})
            state.close()
            with self.assertRaisesRegex(ValueError, 'another experiment'):
                State.for_experiment({**config, 'arm_id': 'B'})
            state = State.for_experiment(config)
            self.assertEqual(state.accepted()['adapter'], 'adapter-A')
            state.close()
            old_path = str(Path(root) / 'historical.sqlite')
            old = State(old_path)
            old.decide('old', 'original', None, True, {})
            old.close()
            with self.assertRaisesRegex(ValueError, 'unscoped'):
                State.for_experiment({**config, 'state_path': old_path})
            old = State(old_path)
            self.assertEqual(old.accepted()['adapter'], 'original')
            old.close()

    def test_config_requires_explicit_namespace_and_path(self):
        for config in [{}, {'study_id': '../unsafe', 'stream_id': 'one', 'arm_id': 'A', 'state_path': '/tmp/no-write'}]:
            with self.assertRaises(ValueError):
                State.for_experiment(config)
