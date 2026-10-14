// Thin task adapter over the same pinned Pi SDK used by the historical pilot.
import { readFileSync, writeFileSync, mkdirSync, realpathSync, appendFileSync, existsSync, lstatSync, readdirSync, readlinkSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { resolve, dirname, relative, sep } from 'node:path';
import { pathToFileURL } from 'node:url';
import { spawn } from 'node:child_process';
import { makeLearningSelectionTool } from './learning-selection.mjs';

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
  if (writing && (request.readonly_paths ?? []).some(p => rel === p || rel.startsWith(p + sep))) throw new Error('Readonly task input');
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
let calls = 0, aborted = false, currentSession, resourceStop, executionWallStart, executionMonotonicStart;
let lastFailedCommand, repeatedFailures = 0;
function mutableWorkspaceHash() {
  const hash = createHash('sha256');
  const visit = dir => {
    for (const name of readdirSync(dir).sort()) {
      const path = resolve(dir, name), rel = relative(cwd, path);
      if ((request.readonly_paths ?? []).some(p => rel === p || rel.startsWith(p + sep))) continue;
      const stat = lstatSync(path);
      hash.update(JSON.stringify([rel, stat.isDirectory() ? 'dir' : stat.isSymbolicLink() ? 'link' : 'file']));
      if (stat.isDirectory()) visit(path);
      else if (stat.isSymbolicLink()) hash.update(readlinkSync(path));
      else if (stat.isFile()) hash.update(readFileSync(path));
    }
  };
  visit(cwd);
  return hash.digest('hex');
}
const tools = [read, write, bash];
if (request.learning_candidates) tools.push(makeLearningSelectionTool(request.learning_candidates,
  request.training_selection_token_budget, resolve(runDir, 'learning-selection.jsonl'), request.training_selection_max_items ?? 2));
for (const tool of tools) {
  const original = tool.execute;
  tool.execute = async (...args) => {
    if (resourceStop) throw new Error('COEVO_REPEAT_FAILURE_STOP: resource protection');
    if (++calls > request.max_tool_calls) { aborted = true; void currentSession?.abort(); throw new Error('Task tool budget exhausted'); }
    const outputs = () => Object.fromEntries((request.allowed_write_paths ?? []).map(path => {
      try { return [path, readFileSync(allowed(path), 'utf8')]; } catch { return [path, null]; }
    }));
    const before = outputs();
    const beforeState = request.repeat_failure_limit ? mutableWorkspaceHash() : undefined;
    let failed = false;
    try {
      const result = await original.apply(tool, args);
      failed = Boolean(result?.isError);
      return result;
    }
    catch (error) { failed = true; throw error; }
    finally {
      if (request.allowed_write_paths !== undefined) appendFileSync(resolve(runDir, 'tool-states.jsonl'),
        JSON.stringify({ tool_call_id: args[0], tool_name: tool.name, before_outputs: before, after_outputs: outputs() }) + '\n');
      if (request.repeat_failure_limit) {
        const afterState = mutableWorkspaceHash();
        const key = JSON.stringify([args[1]?.command, afterState]);
        if (tool.name === 'bash' && failed && beforeState === afterState) {
          repeatedFailures = key === lastFailedCommand ? repeatedFailures + 1 : 1;
          lastFailedCommand = key;
        } else { lastFailedCommand = undefined; repeatedFailures = 0; }
        appendFileSync(resolve(runDir, 'failure-guard.jsonl'), JSON.stringify({ tool_call_id: args[0], tool_name: tool.name,
          failed, before_state: beforeState, after_state: afterState, repeated_failures: repeatedFailures }) + '\n');
        if (repeatedFailures >= request.repeat_failure_limit) {
          aborted = true;
          resourceStop = { reason: 'repeated_failed_command', consecutive: repeatedFailures, state_hash: afterState,
            command_sha256: createHash('sha256').update(args[1].command).digest('hex') };
          writeFileSync(resolve(runDir, 'resource-stop.json'), JSON.stringify(resourceStop, null, 2) + '\n');
        }
      }
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
const reasoningCapable = typeof request.enable_thinking === 'boolean';
const thinkingEnabled = request.enable_thinking === true;
runtime.registerProvider('coevo-local', { api: 'openai-completions', baseUrl: request.endpoint, apiKey: 'local-no-secret',
  models: [{ id: request.model, name: request.model, input: ['text'], reasoning: reasoningCapable,
    contextWindow: request.context_tokens, maxTokens: request.max_output_tokens ?? 4096,
    cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 }, compat: { supportsDeveloperRole: false,
      ...(reasoningCapable ? { thinkingFormat: 'qwen-chat-template', supportsReasoningEffort: false } : {}) } }],
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
let checkpointProvenance;
if (request.resume_entry_id) {
  if (!request.resume_file) throw new Error('Checkpoint selection requires a real parent session');
  const sourceHash = createHash('sha256').update(readFileSync(request.resume_file)).digest('hex');
  const retained = manager.getBranch(request.resume_entry_id);
  if (!retained.length) throw new Error('Unknown checkpoint');
  manager.createBranchedSession(request.resume_entry_id);
  if (JSON.stringify(manager.getBranch()) !== JSON.stringify(retained)) throw new Error('Native checkpoint path changed');
  checkpointProvenance = { source_session: request.resume_file, checkpoint_entry_id: request.resume_entry_id,
    source_sha256: sourceHash, retained_entries: retained.length,
    retained_path_sha256: createHash('sha256').update(JSON.stringify(retained)).digest('hex'),
    retained_messages: retained.filter(e => e.type === 'message').map(e => e.message) };
}
const { session } = await createAgentSession({ cwd: request.model_cwd ?? cwd, agentDir, modelRuntime: runtime,
  model: runtime.getModel('coevo-local', request.model), thinkingLevel: thinkingEnabled ? 'medium' : 'off', resourceLoader: loader,
  noTools: 'builtin', customTools: tools, sessionManager: manager,
  settingsManager: SettingsManager.inMemory({ compaction: { enabled: false }, retry: { enabled: false } }),
});
currentSession = session;
if (checkpointProvenance) {
  checkpointProvenance.native_prefix_equal = JSON.stringify(session.messages) === JSON.stringify(checkpointProvenance.retained_messages);
  checkpointProvenance.source_unchanged = createHash('sha256').update(readFileSync(request.resume_file)).digest('hex') === checkpointProvenance.source_sha256;
  writeFileSync(resolve(runDir, 'checkpoint-provenance.json'), JSON.stringify(checkpointProvenance, null, 2) + '\n');
  if (!checkpointProvenance.native_prefix_equal || !checkpointProvenance.source_unchanged) throw new Error('Native checkpoint provenance mismatch');
}
if (request.sampling || request.capture_payload || request.preview_only || request.repeat_failure_limit) {
  const previousPayloadHook = session.agent.onPayload;
  session.agent.onPayload = async (payload, model) => {
    if (resourceStop) throw new Error(`COEVO_RESOURCE_STOP: ${resourceStop.reason}; no further inference`);
    if (executionMonotonicStart !== undefined && Math.max(performance.now() - executionMonotonicStart, Date.now() - executionWallStart) >= request.timeout_ms) {
      aborted = true;
      resourceStop = { reason: 'wall_timeout', scope: 'checked before further inference' };
      throw new Error('COEVO_WALL_TIMEOUT_STOP: task deadline exceeded before request');
    }
    const prepared = previousPayloadHook ? (await previousPayloadHook(payload, model)) ?? payload : payload;
    const controlled = request.sampling ? { ...prepared, ...request.sampling } : prepared;
    if (request.sampling) appendFileSync(resolve(runDir, 'sampling.jsonl'), JSON.stringify(Object.fromEntries(Object.keys(request.sampling).map(k => [k, controlled[k]]))) + '\n');
    if (request.capture_payload || request.preview_only) appendFileSync(resolve(runDir, 'payloads.jsonl'), JSON.stringify(controlled) + '\n');
    if (request.preview_only) throw new Error('COEVO_PAYLOAD_PREVIEW_ONLY: no inference requested');
    return controlled;
  };
}
const continuationStart = session.messages.length;
executionWallStart = Date.now();
executionMonotonicStart = performance.now();
const timer = setTimeout(() => { aborted = true; resourceStop ??= { reason: 'wall_timeout', scope: 'timer abort' }; void session.abort(); }, request.timeout_ms);
session.subscribe(event => {
  appendFileSync(resolve(runDir, 'events.jsonl'), JSON.stringify(event) + '\n');
});
try {
  for (const prompt of request.prompts) await session.prompt(prompt);
} finally {
  clearTimeout(timer);
  writeFileSync(resolve(runDir, 'transcript.json'), JSON.stringify({ system: session.systemPrompt, messages: session.messages,
    tools: tools.map(t => ({ type: 'function', function: { name: t.name, description: t.description, parameters: t.parameters } })),
    session_file: session.sessionFile, tool_calls: calls, aborted, resource_stop: resourceStop, continuation_start_message_index: continuationStart,
    final_text: session.getLastAssistantText(),
    execution_wall_seconds: (Date.now() - executionWallStart) / 1000,
    execution_monotonic_seconds: (performance.now() - executionMonotonicStart) / 1000 }, null, 2) + '\n');
  session.dispose();
}
if (aborted || session.messages.slice(continuationStart).some(m => m.role === 'assistant' && m.stopReason === 'error')) process.exitCode = 1;
