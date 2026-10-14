import unittest
from coevo.episodes import reconstruct


class EpisodeTests(unittest.TestCase):
    def session(self):
        return {'session_id': 's', 'log_id': 'l', 'workspace': '/project', 'export': 'l.jsonl',
                'isolation_group': 'project', 'environment_kind': 'persistent'}

    def user(self, line, text):
        return {'kind': 'message', 'role': 'user', 'source_line': line, 'text': text}

    def test_goal_wrappers_and_steering_do_not_create_independent_tasks(self):
        records = [self.user(1, 'Inspect CSV'), self.user(2, '<codex_internal_context source="goal"><objective>Inspect CSV</objective>controller rules</codex_internal_context>'),
                   self.user(3, '继续执行'), self.user(4, '<codex_internal_context source="user_goal">status active</codex_internal_context>')]
        episodes, skipped = reconstruct(records, self.session())
        self.assertEqual(len(episodes), 1)
        self.assertEqual(skipped, 1)
        self.assertNotIn('controller rules', str(episodes))
        self.assertEqual(len(episodes[0]['instruction_events']), 3)
        self.assertFalse(episodes[0]['train_ready'])

    def test_async_results_stay_with_original_task(self):
        records = [self.user(1, 'Task A'),
                   {'kind': 'tool_call', 'source_line': 2, 'call_id': 'c', 'paired': True, 'input': '{}'},
                   self.user(3, 'Task B'),
                   {'kind': 'tool_result', 'source_line': 4, 'call_id': 'c', 'paired': True, 'output': 'exit 0'},
                   {'kind': 'message', 'source_line': 5, 'role': 'assistant', 'phase': 'final_answer', 'text': 'done'}]
        episodes, _ = reconstruct(records, self.session())
        self.assertEqual(len(episodes), 2)
        self.assertEqual(episodes[0]['records'][-1]['call_id'], 'c')
        self.assertEqual(episodes[0]['cross_episode_results'][0]['source_line'], 4)
        self.assertEqual(episodes[1]['outcome'], 'not-independently-verified')
        self.assertEqual(episodes[1]['final_response_refs'], [5])

    def test_duplicate_snapshots_retain_shared_source_cluster(self):
        a, _ = reconstruct([self.user(1, 'same original request')], self.session())
        b, _ = reconstruct([self.user(19, 'same original request')], {**self.session(), 'log_id': 'copy'})
        self.assertEqual(a[0]['source_cluster_id'], b[0]['source_cluster_id'])
        self.assertNotEqual(a[0]['episode_id'], b[0]['episode_id'])
