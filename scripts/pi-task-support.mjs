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
