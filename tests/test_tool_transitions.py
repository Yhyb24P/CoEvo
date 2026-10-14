import unittest
from coevo.tool_transitions import commands, returned_results, readonly, mapping


class ToolTransitionTests(unittest.TestCase):
    def test_literal_wrappers_are_converted_without_executing_code(self):
        record = {'tool': 'exec', 'call_id': 'c', 'input': 'text(await tools.exec_command({cmd:"ls",workdir:"/source",login:false}));\ntext(await tools.exec_command({cmd:"pwd"}));'}
        result = {'output': [{'text': 'Script completed'}, {'text': '{"exit_code":0,"output":"file"}'}, {'text': '{"exit_code":0,"output":"/source"}'}]}
        self.assertEqual(len(commands(record)), 2)
        target, observations, eligible = mapping(record, result, '/source')
        self.assertTrue(eligible)
        self.assertEqual(len(target['tool_calls']), 2)
        self.assertEqual(len(observations), 2)
        for script in ['text(await tools.exec_command({cmd:secretVariable}));', 'text(await tools.exec_command({cmd:"pwd"})); fetch("secret");', 'text(await tools.exec_command({cmd:"pwd",cmd:"rm -rf ."}));']:
            with self.assertRaises(ValueError):
                commands({**record, 'input': script})

    def test_only_successful_read_queries_are_positive_targets(self):
        for command in ['cd /source && sed -n "1,90p" file.py', 'rg --files | head -20', 'git -C /source status --short']:
            self.assertTrue(readonly(command), command)
        for command in ['rm file', 'echo x > file', 'sed -i x file', 'python run.py', 'ls $(cat auth.json)', 'git config --list', 'git diff', 'sed -n "1p;w output" file', 'curl example.invalid']:
            self.assertFalse(readonly(command), command)
        record = {'tool': 'exec_command', 'call_id': 'c', 'input': '{"cmd":"ls"}'}
        _, _, eligible = mapping(record, {'output': '{"exit_code":1,"output":"denied"}'}, '/source')
        self.assertFalse(eligible)
        with self.assertRaises(ValueError):
            returned_results({'output': '{"exit_code":0,"output":"a"}'}, 2)
