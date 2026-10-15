import test from 'node:test';
import assert from 'node:assert/strict';
import { classifyPiOutcome, installedPiVersion } from '../scripts/pi-task-support.mjs';

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
