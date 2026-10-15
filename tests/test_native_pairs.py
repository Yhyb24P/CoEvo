import copy
import unittest

from coevo.extract import native_tool_pairs
from coevo.train import normalize_messages


class NativePairTests(unittest.TestCase):
    def fixture(self):
        prefix = [{'role': 'user', 'content': 'Inspect the actual input.'}]
        target = {'role': 'assistant', 'content': None, 'reasoning': 'Not certified.',
                  'tool_calls': [{'id': 'c1', 'type': 'function', 'function': {
                      'name': 'read', 'arguments': '{"path":"input.csv"}'}}]}
        observation = {'role': 'tool', 'tool_call_id': 'c1', 'content': 'real data'}
        payloads = [{'messages': prefix, 'tools': []},
                    {'messages': prefix + [target, observation], 'tools': []}]
        transcript = {'messages': [{'role': 'toolResult', 'toolCallId': 'c1',
                                    'content': 'real data', 'isError': False}]}
        return payloads, transcript

    def test_pair_retains_actual_context_and_unverified_reasoning(self):
        payloads, transcript = self.fixture()
        pair, = native_tool_pairs(payloads, transcript)
        self.assertEqual(pair['prefix'], payloads[0]['messages'])
        self.assertNotIn('real data', str(pair['prefix']))
        self.assertEqual(pair['target']['reasoning'], 'Not certified.')
        self.assertFalse(pair['independently_verified'])
        self.assertEqual(pair['tool_errors'], [False])

    def test_changed_history_or_tool_schema_is_not_reconstructed(self):
        for change in ('history', 'tools'):
            payloads, transcript = self.fixture()
            if change == 'history':
                payloads[1]['messages'][0] = {'role': 'user', 'content': 'rewritten'}
            else:
                payloads[1]['tools'] = [{'invented': 'tool'}]
            with self.assertRaises(ValueError):
                native_tool_pairs(payloads, transcript)

    def test_unmatched_observation_is_rejected_and_errors_stay_errors(self):
        payloads, transcript = self.fixture()
        transcript['messages'][0]['isError'] = True
        self.assertEqual(native_tool_pairs(payloads, transcript)[0]['tool_errors'], [True])
        payloads[1]['messages'][-1]['tool_call_id'] = 'other'
        with self.assertRaises(ValueError):
            native_tool_pairs(payloads, transcript)

    def test_native_reasoning_alias_matches_vllm_without_mutating_wire_data(self):
        payloads, _ = self.fixture()
        messages = copy.deepcopy(payloads[1]['messages'])
        normalized = normalize_messages(messages)
        self.assertEqual(normalized[1]['reasoning_content'], 'Not certified.')
        self.assertNotIn('reasoning_content', messages[1])
        self.assertEqual(normalized[1]['tool_calls'][0]['function']['arguments'], {'path': 'input.csv'})
        messages[1]['reasoning_content'] = 'conflicting text'
        with self.assertRaises(ValueError):
            normalize_messages(messages)


if __name__ == '__main__':
    unittest.main()
