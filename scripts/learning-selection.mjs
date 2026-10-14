import { appendFileSync } from 'node:fs';

// Learning prose stays free. This tool only executes a reference/budget decision.
export function makeLearningSelectionTool(candidates, budget, ledgerPath, maxItems = 2) {
  return {
    name: 'nominate_training', label: 'Nominate verified training actions',
    description: 'Select or withdraw existing verified Assistant actions for training consideration. Indices are 1-based; an empty list withdraws selection. This does not launch training or change admission rules.',
    parameters: { type: 'object', properties: { indices: { type: 'array', items: { type: 'integer', minimum: 1 } } }, required: ['indices'], additionalProperties: false },
    execute: async (_callId, args) => {
      const indices = args.indices;
      let error;
      if (!Array.isArray(indices) || indices.some(i => !Number.isInteger(i) || i < 1 || i > candidates.length)) error = 'Reference is outside this verified source pool';
      else if (new Set(indices).size !== indices.length || indices.length > maxItems) error = 'Duplicate references or item budget exceeded';
      const selected = error ? [] : indices.map(i => candidates[i - 1]);
      const tokens = selected.reduce((total, c) => total + c.supervised_tokens, 0);
      if (!error && tokens > budget) error = 'Supervised token budget exceeded; choose fewer complete targets';
      const decision = { accepted: !error, error: error ?? null, indices, supervised_tokens: tokens,
        selected_ids: error ? [] : selected.map(c => c.candidate_id), budget, max_items: maxItems };
      appendFileSync(ledgerPath, JSON.stringify(decision) + '\n');
      return { content: [{ type: 'text', text: JSON.stringify(decision) }], details: decision };
    },
  };
}
