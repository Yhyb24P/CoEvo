import copy
import json
import tempfile
import unittest
from pathlib import Path

from coevo.everyday import prepare, verify
from coevo.behavior import certify
from coevo.train import admit


def assistant_call(name, call_id, args):
    return {'role': 'assistant', 'stopReason': 'toolUse', 'content': [
        {'type': 'text', 'text': 'unverified intermediate explanation'},
        {'type': 'toolCall', 'id': call_id, 'name': name, 'arguments': args}]}


def fixture(task, out, fail_first=False):
    path, original = next(iter(task['inputs'].items()))
    name, expected = next(iter(task['expected'].items()))
    messages = [{'role': 'user', 'content': task['prompt']}, assistant_call('read', 'r1', {'path': path}),
        {'role': 'toolResult', 'toolCallId': 'r1', 'content': [{'type': 'text', 'text': original}], 'isError': False}]
    if fail_first:
        messages += [assistant_call('write', 'bad', {'path': name, 'content': 'wrong output'}),
            {'role': 'toolResult', 'toolCallId': 'bad', 'content': [{'type': 'text', 'text': 'write rejected'}], 'isError': True}]
    messages += [assistant_call('write', 'w1', {'path': name, 'content': expected}),
        {'role': 'toolResult', 'toolCallId': 'w1', 'content': [{'type': 'text', 'text': 'written'}], 'isError': False},
        {'role': 'assistant', 'stopReason': 'stop', 'content': [{'type': 'text', 'text': '已完成'}]}]
    transcript = {'system': 'synthetic unit-test fixture; not model evidence', 'tools': [], 'messages': messages,
                  'final_text': '已完成', 'aborted': False}
    (out / 'transcript.json').write_text(json.dumps(transcript, ensure_ascii=False))
    for filename, content in task['expected'].items():
        (Path(task['workspace']) / filename).write_text(content)


class EverydayTests(unittest.TestCase):
    def test_discussion_records_natural_response_without_certifying_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/'run';task=prepare(out,'normalize')
            fixture(task,out)
            task={**task,'action':'discuss','expected':{}}
            trace=json.loads((out/'transcript.json').read_text())
            trace['final_text']='我应该使用清单路径，不追加历史目录。'
            trace['messages'][-1]['content']=[{'type':'text','text':trace['final_text']}]
            (out/'transcript.json').write_text(json.dumps(trace))
            result=verify(task,out)
            self.assertTrue(result['passed'])
            self.assertIn('recording only',result['response_check_scope'])
            self.assertNotIn('stop',[c['behavior_kind'] for c in certify(task,out)])

    def test_readback_requires_correct_observed_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'run'
            task = prepare(out, 'normalize')
            fixture(task, out)
            trace = json.loads((out / 'transcript.json').read_text())
            path, expected = next(iter(task['expected'].items()))
            trace['messages'][-1:-1] = [assistant_call('read', 'check', {'path': path}),
                {'role': 'toolResult', 'toolCallId': 'check', 'content': [{'type': 'text', 'text': expected}], 'isError': False}]
            (out / 'transcript.json').write_text(json.dumps(trace))
            self.assertTrue(verify(task, out)['passed'])
            self.assertIn('readback', [c['behavior_kind'] for c in certify(task, out)])
            trace['messages'][-2]['content'][0]['text'] = 'wrong observed output'
            (out / 'transcript.json').write_text(json.dumps(trace))
            self.assertNotIn('readback', [c['behavior_kind'] for c in certify(task, out)])

    def test_failed_episode_can_supply_verified_read_but_not_false_stop(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'run'
            task = prepare(out, 'normalize')
            fixture(task, out)
            transcript = json.loads((out / 'transcript.json').read_text())
            # A successful tool execution with objectively wrong CSV must not be imitated.
            transcript['messages'][3]['content'][-1]['arguments']['content'] = 'wrong output'
            (out / 'transcript.json').write_text(json.dumps(transcript, ensure_ascii=False))
            (Path(task['workspace']) / 'outputs/cleaned.csv').write_text('wrong output')
            self.assertFalse(verify(task, out)['passed'])
            candidates = certify(task, out)
            self.assertEqual([x['behavior_kind'] for x in candidates], ['read'])
            self.assertIs(admit(candidates[0]), candidates[0])
    def test_result_and_protected_input_are_both_required(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'run'
            task = prepare(out, 'normalize')
            fixture(task, out)
            self.assertTrue(verify(task, out)['passed'])
            (Path(task['workspace']) / 'expenses.csv').write_text('changed source')
            result = verify(task, out)
            self.assertFalse(result['passed'])
            self.assertEqual(result['unauthorized_changes'], ['expenses.csv'])

    def test_failed_actions_are_context_not_positive_targets(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'run'
            task = prepare(out, 'normalize')
            fixture(task, out, fail_first=True)
            self.assertTrue(verify(task, out)['passed'])
            candidates = certify(task, out)
            self.assertEqual([x['behavior_kind'] for x in candidates], ['read', 'write', 'stop'])
            self.assertIsNone(candidates[0]['target']['content'])
            self.assertTrue(any(m.get('role') == 'tool' and m.get('tool_call_id') == 'bad' for m in candidates[-1]['prefix']))
            for candidate in candidates:
                self.assertIs(admit(candidate), candidate)
            mutated = copy.deepcopy(candidates[0])
            mutated['prefix'][0]['content'] += ' altered'
            with self.assertRaises(ValueError):
                admit(mutated)
            mutated = copy.deepcopy(candidates[-1])
            mutated['target']['content'] = 'different claim'
            with self.assertRaises(ValueError):
                admit(mutated)
            with self.assertRaises(ValueError):
                admit({**candidates[0], 'split': 'D'})

    def test_ask_case_has_no_training_candidates(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'run'
            task = prepare(out, 'missing_rate')
            text = '请提供美元兑人民币的汇率？'
            (out / 'transcript.json').write_text(json.dumps({'final_text': text, 'aborted': False,
                'messages': [{'role': 'assistant', 'stopReason': 'stop', 'content': [{'type': 'text', 'text': text}]}]}))
            self.assertTrue(verify(task, out)['passed'])
            self.assertEqual(certify(task, out), [])
