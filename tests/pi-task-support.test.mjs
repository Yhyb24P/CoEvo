import test from 'node:test';
import assert from 'node:assert/strict';
import { classifyPiOutcome, installedPiVersion, allocateContextOutput, countAndAllocateContext } from '../scripts/pi-task-support.mjs';

test('only a normally stopped final assistant is complete', () => {
  assert.deepEqual(classifyPiOutcome([{ role: 'assistant', stopReason: 'toolUse' },
    { role: 'tool' }, { role: 'assistant', stopReason: 'stop' }]),
    { complete: true, stop_reason: 'stop', incomplete_reason: null });
});

test('truncation, failure, and an unfinished tool turn remain incomplete', () => {
  for (const reason of ['length', 'error', 'aborted', 'toolUse', 'deferred']) {
    const outcome = classifyPiOutcome([{ role: 'assistant', stopReason: reason }]);
    assert.equal(outcome.complete, false);
    assert.equal(outcome.incomplete_reason, reason);
  }
});

test('resource stop and missing response are not successful', () => {
  assert.equal(classifyPiOutcome([{ role: 'assistant', stopReason: 'stop' }],
    { resourceStop: { reason: 'wall_timeout' } }).incomplete_reason, 'wall_timeout');
  assert.equal(classifyPiOutcome([{ role: 'assistant', stopReason: 'stop' }], { aborted: true }).complete, false);
  assert.equal(classifyPiOutcome([]).incomplete_reason, 'missing_final_assistant');
});

test('do not guess installed SDK version for an unknown entry', () => {
  assert.equal(installedPiVersion('/tmp/coevo-not-installed/dist/index.js'), null);
});

test('real rejected-request count fits by changing only the output ceiling', () => {
  const original = { model: 'W0', messages: [{ role: 'user', content: 'actual context' }],
    tools: [], max_completion_tokens: 26105 };
  const { payload, budget } = allocateContextOutput(original,
    { count: 123501, max_model_len: 139264 }, 139264);
  assert.equal(payload.max_completion_tokens, 15763);
  assert.equal(budget.prompt_tokens + payload.max_completion_tokens, 139264);
  assert.equal(original.max_completion_tokens, 26105);
  assert.equal(payload.messages, original.messages);
  assert.equal(payload.tools, original.tools);
});

test('honor smaller configured capacity and existing per-turn ceiling', () => {
  assert.equal(allocateContextOutput({ max_tokens: 50 },
    { count: 100, max_model_len: 1000 }, 500).payload.max_tokens, 50);
  assert.equal(allocateContextOutput({ max_tokens: 600 },
    { count: 100, max_model_len: 1000 }, 500).payload.max_tokens, 400);
  assert.throws(() => allocateContextOutput({ max_tokens: 10 },
    { count: 500, max_model_len: 1000 }, 500),
    error => error.code === 'COEVO_CONTEXT_CAPACITY_EXHAUSTED' && error.budget.allocated_output_tokens === 0);
});

test('invalid counts or ambiguous output ceilings never use an estimate', () => {
  assert.throws(() => allocateContextOutput({ max_tokens: 10 }, { count: -1, max_model_len: 100 }, 100));
  assert.throws(() => allocateContextOutput({ max_tokens: 10, max_completion_tokens: 10 },
    { count: 1, max_model_len: 100 }, 100));
});

test('tokenize the actual tools and template on the configured service origin', async () => {
  const original = { model: 'W0', messages: [{ role: 'user', content: 'current task' }],
    tools: [{ type: 'function', function: { name: 'read' } }],
    chat_template_kwargs: { enable_thinking: true }, max_completion_tokens: 80, seed: 17 };
  const result = await countAndAllocateContext(original, 'http://127.0.0.2:18000/v1', 100, {
    fetchImpl: async (url, options) => {
      assert.equal(url.href, 'http://127.0.0.2:18000/tokenize');
      const body = JSON.parse(options.body);
      assert.deepEqual(body.messages, original.messages);
      assert.deepEqual(body.tools, original.tools);
      assert.deepEqual(body.chat_template_kwargs, original.chat_template_kwargs);
      assert.equal(body.add_generation_prompt, true);
      assert.equal(body.max_completion_tokens, undefined);
      assert.equal(options.redirect, 'error');
      return new Response(JSON.stringify({ count: 70, max_model_len: 100 }));
    },
  });
  assert.equal(result.payload.max_completion_tokens, 30);
  assert.equal(result.payload.seed, 17);
  await assert.rejects(() => countAndAllocateContext(original, 'http://127.0.0.2:18000/v1', 100,
    { fetchImpl: async () => new Response('unavailable', { status: 503 }) }), /HTTP 503/);
});
