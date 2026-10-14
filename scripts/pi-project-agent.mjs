// Thin task adapter over the same pinned Pi SDK used by the historical pilot.
import { readFileSync, writeFileSync, mkdirSync, realpathSync, appendFileSync, existsSync, lstatSync } from 'node:fs';
import { resolve, dirname, relative, sep } from 'node:path';
import { pathToFileURL } from 'node:url';
import { spawn } from 'node:child_process';

const request = JSON.parse(readFileSync(process.env.COEVO_REQUEST_FILE, 'utf8'));
const { createAgentSession, createExtensionRuntime, ModelRuntime, SessionManager, SettingsManager,
  createReadToolDefinition, createWriteToolDefinition, createBashToolDefinition } = await import(pathToFileURL(request.pi_entry));
const cwd = realpathSync(request.workspace);
const runDir = resolve(request.run_dir);
mkdirSync(runDir, { recursive: true });
const agentDir = resolve(runDir, 'agent-state');
mkdirSync(agentDir, { recursive: true });
const authPath = resolve(agentDir, 'auth.json');
writeFileSync(authPath, '{}\n');
function allowed(path, writing = false) {
  const mapped = path === '/workspace' || path.startsWith('/workspace/') ? '.' + path.slice('/workspace'.length) : path;
  const absolute = resolve(cwd, mapped);
  const rel = relative(cwd, absolute);
  if (!rel || rel === '..' || rel.startsWith('..' + sep) || rel.startsWith(sep)) throw new Error('Path outside task workspace');
  if (writing && request.allowed_write_paths !== undefined && !request.allowed_write_paths.includes(rel)) throw new Error('No write permission for this task path');
  let current = cwd;
  for (const part of rel.split(sep)) {
    current = resolve(current, part);
    try {
      if (lstatSync(current).isSymbolicLink()) throw new Error('Task symlinks are not authorized');
    } catch (error) { if (error.code !== 'ENOENT') throw error; }
  }
  return absolute;
}
const read = createReadToolDefinition(cwd, { operations: {
  access: async path => { allowed(path); }, readFile: async path => readFileSync(allowed(path)),
  detectImageMimeType: async () => undefined,
}});
const write = createWriteToolDefinition(cwd, { operations: {
  mkdir: async path => {
    if (resolve(path) === cwd || resolve(path) === '/workspace') return;
    const target = allowed(path);
    if (request.allowed_write_paths !== undefined) {
      if (!existsSync(target)) throw new Error('Task directories must already exist');
    } else mkdirSync(target, { recursive: true });
  },
  writeFile: async (path, content) => writeFileSync(allowed(path, true), content),
}});
const bash = createBashToolDefinition(cwd, { exposeSessionEnvironment: false, operations: {
  exec: async (command, _cwd, { onData, signal, timeout }) => {
    const args = [...request.sandbox_prefix.slice(1), '/bin/bash', '--noprofile', '--norc', '-c', command];
    if (signal?.aborted) throw new Error('aborted');
    return await new Promise((accept, reject) => {
      const child = spawn('bwrap', args, { detached: true, stdio: ['ignore', 'pipe', 'pipe'] });
      const abort = () => { if (child.pid) { try { process.kill(-child.pid, 'SIGKILL'); } catch {} } };
      const timer = setTimeout(abort, Math.min(timeout ?? 60, 120) * 1000);
      signal?.addEventListener('abort', abort, { once: true });
      child.stdout.on('data', onData); child.stderr.on('data', onData);
      const clean = () => { clearTimeout(timer); signal?.removeEventListener('abort', abort); };
      child.on('error', error => { clean(); reject(error); });
      child.on('close', code => { clean(); accept({ exitCode: code ?? 137 }); });
    });
  },
}});
let calls = 0, aborted = false, currentSession;
const tools = [read, write, bash];
for (const tool of tools) {
  const original = tool.execute;
  tool.execute = async (...args) => {
    if (++calls > request.max_tool_calls) { aborted = true; void currentSession?.abort(); throw new Error('Task tool budget exhausted'); }
    const outputs = () => Object.fromEntries((request.allowed_write_paths ?? []).map(path => {
      try { return [path, readFileSync(allowed(path), 'utf8')]; } catch { return [path, null]; }
    }));
    const before = outputs();
    try { return await original.apply(tool, args); }
    finally {
      if (request.allowed_write_paths !== undefined) appendFileSync(resolve(runDir, 'tool-states.jsonl'),
        JSON.stringify({ tool_call_id: args[0], tool_name: tool.name, before_outputs: before, after_outputs: outputs() }) + '\n');
    }
  };
}
if (request.tool_probe) {
  const results = [];
  for (const probe of request.tool_probe) {
    try { results.push({ result: await tools.find(t => t.name === probe.name).execute('probe', probe.arguments) }); }
    catch (error) { results.push({ error: error.message }); }
  }
  writeFileSync(resolve(runDir, 'tool-probe.json'), JSON.stringify(results, null, 2));
  process.exit(0);
}
const runtime = await ModelRuntime.create({ authPath, modelsPath: null, refreshOnCreate: false, allowModelNetwork: false });
runtime.registerProvider('coevo-local', { api: 'openai-completions', baseUrl: request.endpoint, apiKey: 'local-no-secret',
  models: [{ id: request.model, name: request.model, input: ['text'], reasoning: false,
    contextWindow: request.context_tokens, maxTokens: request.max_output_tokens ?? 4096,
    cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 }, compat: { supportsDeveloperRole: false } }],
});
const systemPrompt = request.system_prompt;
const loader = {
  getExtensions: () => ({ extensions: [], errors: [], runtime: createExtensionRuntime() }),
  getSkills: () => ({ skills: [], diagnostics: [] }), getPrompts: () => ({ prompts: [], diagnostics: [] }),
  getThemes: () => ({ themes: [], diagnostics: [] }), getAgentsFiles: () => ({ agentsFiles: [] }),
  getSystemPrompt: () => systemPrompt, getSystemPromptSource: () => undefined,
  getAppendSystemPrompt: () => [], getAppendSystemPromptSources: () => [], extendResources: () => {}, reload: async () => {},
};
const manager = request.resume_file ? SessionManager.forkFrom(request.resume_file, cwd, resolve(runDir, 'sessions')) : SessionManager.create(cwd, resolve(runDir, 'sessions'));
const { session } = await createAgentSession({ cwd: request.model_cwd ?? cwd, agentDir, modelRuntime: runtime,
  model: runtime.getModel('coevo-local', request.model), thinkingLevel: 'off', resourceLoader: loader,
  noTools: 'builtin', customTools: tools, sessionManager: manager,
  settingsManager: SettingsManager.inMemory({ compaction: { enabled: false }, retry: { enabled: false } }),
});
currentSession = session;
if (request.sampling) {
  const previousPayloadHook = session.agent.onPayload;
  session.agent.onPayload = async (payload, model) => {
    const prepared = previousPayloadHook ? (await previousPayloadHook(payload, model)) ?? payload : payload;
    const controlled = { ...prepared, temperature: request.sampling.temperature, seed: request.sampling.seed };
    appendFileSync(resolve(runDir, 'sampling.jsonl'), JSON.stringify({ temperature: controlled.temperature, seed: controlled.seed }) + '\n');
    return controlled;
  };
}
const continuationStart = session.messages.length;
const timer = setTimeout(() => { aborted = true; void session.abort(); }, request.timeout_ms);
session.subscribe(event => {
  appendFileSync(resolve(runDir, 'events.jsonl'), JSON.stringify(event) + '\n');
});
try {
  for (const prompt of request.prompts) await session.prompt(prompt);
} finally {
  clearTimeout(timer);
  writeFileSync(resolve(runDir, 'transcript.json'), JSON.stringify({ system: session.systemPrompt, messages: session.messages,
    tools: tools.map(t => ({ type: 'function', function: { name: t.name, description: t.description, parameters: t.parameters } })),
    session_file: session.sessionFile, tool_calls: calls, aborted, continuation_start_message_index: continuationStart,
    final_text: session.getLastAssistantText() }, null, 2) + '\n');
  session.dispose();
}
if (aborted || session.messages.slice(continuationStart).some(m => m.role === 'assistant' && m.stopReason === 'error')) process.exitCode = 1;
