// Independent of Pi's interactive/print-mode exit code.
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';

export function installedPiVersion(entry) {
  try {
    const pkg = JSON.parse(readFileSync(resolve(dirname(entry), '..', 'package.json'), 'utf8'));
    return pkg.name === '@earendil-works/pi-coding-agent' && typeof pkg.version === 'string'
      ? pkg.version : null;
  } catch {
    return null;
  }
}

export function classifyPiOutcome(messages, { aborted = false, resourceStop = null } = {}) {
  const final = messages.filter(m => m?.role === 'assistant').at(-1);
  const stopReason = final?.stopReason ?? null;
  const incompleteReason = resourceStop?.reason ?? (aborted ? 'aborted' :
    stopReason === 'stop' ? null : stopReason ?? 'missing_final_assistant');
  return { complete: incompleteReason === null, stop_reason: stopReason, incomplete_reason: incompleteReason };
}

export function allocateContextOutput(payload, counted, configuredCapacity) {
  if (!Number.isSafeInteger(counted?.count) || counted.count < 0 ||
      !Number.isSafeInteger(counted?.max_model_len) || counted.max_model_len <= 0 ||
      !Number.isSafeInteger(configuredCapacity) || configuredCapacity <= 0)
    throw new Error('Invalid authoritative context count or capacity');
  const fields = ['max_completion_tokens', 'max_tokens'].filter(k => payload[k] !== undefined);
  if (fields.length !== 1 || !Number.isSafeInteger(payload[fields[0]]) || payload[fields[0]] <= 0)
    throw new Error('Expected one positive output ceiling');
  const field = fields[0];
  const capacity = Math.min(configuredCapacity, counted.max_model_len);
  const allocated = Math.min(payload[field], Math.max(0, capacity - counted.count));
  const budget = { prompt_tokens: counted.count, capacity,
    requested_output_tokens: payload[field], allocated_output_tokens: allocated };
  if (!allocated) {
    const error = new Error('COEVO_CONTEXT_CAPACITY_EXHAUSTED: no output room remains');
    error.code = 'COEVO_CONTEXT_CAPACITY_EXHAUSTED';
    error.budget = budget;
    throw error;
  }
  return { payload: { ...payload, [field]: allocated }, budget };
}

export async function countAndAllocateContext(payload, endpoint, capacity,
    { fetchImpl = fetch, timeoutMs = 10000 } = {}) {
  const url = new URL(endpoint);
  if (!/\/v1\/?$/.test(url.pathname) || url.username || url.password)
    throw new Error('Expected the configured vLLM /v1 endpoint');
  url.pathname = url.pathname.replace(/\/v1\/?$/, '/tokenize');
  url.search = ''; url.hash = '';
  const body = { add_generation_prompt: true, add_special_tokens: false };
  for (const key of ['model', 'messages', 'tools', 'chat_template_kwargs', 'chat_template',
    'add_generation_prompt', 'continue_final_message', 'add_special_tokens',
    'mm_processor_kwargs', 'media_io_kwargs']) {
    if (payload[key] !== undefined) body[key] = payload[key];
  }
  const response = await fetchImpl(url, { method: 'POST',
    headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
    signal: AbortSignal.timeout(timeoutMs), redirect: 'error' });
  if (!response.ok) throw new Error(`Authoritative tokenization failed: HTTP ${response.status}`);
  return allocateContextOutput(payload, await response.json(), capacity);
}
