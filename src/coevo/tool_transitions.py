"""Verified archived tool interactions, independent of whole-task success.

Literal-only conversion: never evaluates historical JavaScript or shell commands.
Only successful read-only queries are currently eligible positive targets; other
supported shell actions can remain real history, without being marked correct.
"""
import json
import re
import shlex
from pathlib import Path
from .codex_export import sha

DECODER = json.JSONDecoder()
PREFIX = re.compile(r'\s*text\(\s*await\s+tools\.exec_command\(\s*')
SUFFIX = re.compile(r'\s*\)\s*\)\s*;?')


def literal_object(text, position=0):
    if text[position:position+1] != '{':
        raise ValueError('Only literal objects are supported')
    position += 1
    values = {}
    while True:
        position += len(text[position:]) - len(text[position:].lstrip())
        if text[position:position+1] == '}':
            return values, position+1
        if text[position:position+1] == '"':
            key, size = DECODER.raw_decode(text[position:])
            position += size
        else:
            match = re.match(r'[A-Za-z_][A-Za-z0-9_]*', text[position:])
            if not match:
                raise ValueError('Dynamic or unsupported JavaScript property')
            key = match.group(); position += len(key)
        position += len(text[position:]) - len(text[position:].lstrip())
        if text[position:position+1] != ':':
            raise ValueError('Missing literal property value')
        position += 1
        position += len(text[position:]) - len(text[position:].lstrip())
        value, size = DECODER.raw_decode(text[position:])
        if not isinstance(value, (str, int, float, bool, type(None))):
            raise ValueError('Only scalar command arguments are supported')
        if key in values:
            raise ValueError('Duplicate property')
        values[key] = value; position += size
        position += len(text[position:]) - len(text[position:].lstrip())
        if text[position:position+1] == ',':
            position += 1
        elif text[position:position+1] != '}':
            raise ValueError('Unsupported expression in command object')


def commands(record):
    if record.get('tool') == 'exec_command':
        value = json.loads(record['input'])
        if not isinstance(value, dict):
            raise ValueError('Command arguments must be an object')
        return [value]
    if record.get('tool') != 'exec':
        raise ValueError('Tool mapping not implemented')
    text = record['input']
    text = re.sub(r'^\s*// @exec:[^\n]*\n', '', text)
    result, position = [], 0
    while text[position:].strip():
        prefix = PREFIX.match(text, position)
        if not prefix:
            raise ValueError('Only serial literal exec_command wrappers are supported')
        value, position = literal_object(text, prefix.end())
        suffix = SUFFIX.match(text, position)
        if not suffix:
            raise ValueError('Unsupported wrapper expression')
        result.append(value); position = suffix.end()
    if not result:
        raise ValueError('No wrapped commands')
    return result


def returned_results(record, count):
    output = record.get('output')
    if isinstance(output, list):
        texts = [x.get('text', '') for x in output if isinstance(x, dict)]
    elif isinstance(output, str):
        texts = [output]
    else:
        texts = [json.dumps(output)]
    results = []
    for text in texts:
        try:
            value = json.loads(text)
        except (ValueError, TypeError):
            continue
        if isinstance(value, dict) and 'output' in value and ('exit_code' in value or 'session_id' in value):
            results.append(value)
    if len(results) == count:
        return results
    if count == 1 and isinstance(output, str):
        # Older native tool UI returns a rendered status envelope, not JSON.
        match = re.search(r'Process exited with code (-?\d+)\b', output)
        if match:
            return [{'exit_code': int(match.group(1)), 'output': output}]
    raise ValueError('Cannot pair command arguments with actual result envelopes')


def readonly(command):
    if not isinstance(command, str) or not command.strip():
        return False
    if re.search(r'[<>`$\n]', command) or re.search(r'(?i)(auth\.json|credentials|id_rsa|\.env\b|(?:^|/)H(?:/|\b))', command):
        return False
    try:
        lexer = shlex.shlex(command, posix=True, punctuation_chars=';&|')
        lexer.whitespace_split = True
        tokens = list(lexer)
    except ValueError:
        return False
    segments, current = [], []
    for token in tokens:
        if token in (';', '&&', '|'):
            if not current:
                return False
            segments.append(current); current = []
        elif token in ('&', '||'):
            return False
        else:
            current.append(token)
    if current:
        segments.append(current)
    if not segments:
        return False
    for parts in segments:
        program = parts[0]
        if program == 'cd':
            if len(parts) != 2 or parts[1].startswith('-'):
                return False
        elif program in ('pwd', 'ls', 'cat', 'head', 'tail', 'wc'):
            pass
        elif program in ('rg', 'grep'):
            if any(x.startswith('--pre') for x in parts):
                return False
        elif program == 'sed':
            if any(x == '-i' or x.startswith('--in-place') for x in parts) or '-n' not in parts:
                return False
            # Restrict script to numeric line selections, not write/execute commands.
            scripts = [x for x in parts[1:] if re.fullmatch(r'\d+(?:,\d+)?p', x)]
            if len(scripts) != 1 or any(x.startswith(('-e', '-f')) for x in parts):
                return False
        elif program == 'git':
            args = parts[1:]
            if args[:1] == ['-C'] and len(args) >= 3:
                args = args[2:]
            if not args or args[0] not in ('status', 'diff', 'rev-parse', 'ls-files'):
                return False
            if any(x.startswith(('--output', '--ext-diff', '--textconv')) for x in args):
                return False
            if args[0] == 'diff' and '--no-ext-diff' not in args:
                # Preserve the actual command, never quietly add a flag.
                return False
        else:
            return False
    return True


def mapping(record, result, workspace):
    args = commands(record)
    results = returned_results(result, len(args))
    calls, observations = [], []
    for index, (arg, outcome) in enumerate(zip(args, results)):
        if not isinstance(arg.get('cmd'), str) or not isinstance(arg.get('workdir', workspace), str):
            raise ValueError('Unsupported command or cwd')
        cwd = arg.get('workdir', workspace)
        base = Path(workspace)
        if not Path(cwd).is_absolute() or not Path(cwd).is_relative_to(base):
            raise ValueError('Command cwd cannot be mapped within the recorded workspace')
        virtual_cwd = '/workspace' + (('/' + str(Path(cwd).relative_to(base))) if Path(cwd) != base else '')
        command = arg['cmd'].replace(workspace, '/workspace')
        if virtual_cwd != '/workspace':
            command = 'cd ' + shlex.quote(virtual_cwd) + ' && ' + command
        call_id = record['call_id'] + '-' + str(index)
        calls.append({'id': call_id, 'type': 'function', 'function': {
            'name': 'bash', 'arguments': json.dumps({'command': command}, ensure_ascii=False)}})
        # Preserve real return, including errors/running handles; it is observation,
        # not a supervised correctness label. Wrapper metadata remains in evidence.
        observations.append({'role': 'tool', 'tool_call_id': call_id,
                             'content': json.dumps(outcome, ensure_ascii=False)})
    eligible = all(readonly(arg['cmd']) and outcome.get('exit_code') == 0 and not outcome.get('session_id')
                   and not arg.get('tty') and arg.get('sandbox_permissions') != 'require_escalated'
                   and not re.search(r'/(?:home|mnt)/', call['function']['arguments'])
                   for arg, outcome, call in zip(args, results, calls))
    return {'role': 'assistant', 'content': None, 'tool_calls': calls}, observations, eligible
