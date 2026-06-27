import { format } from 'date-fns';
import type { ModelRun, PoolConfig } from '../types';

/** Long-form prediction-model names, keyed by short tag (lowercased). */
export const MODEL_LABELS: Record<string, string> = {
  v2: 'V2 — Market-calibrated',
  v1: 'V1 — Dixon-Coles',
};

/** Normalize a stored model_version (e.g. "v2", "2.1.0") to a short tag like "V2". */
export function modelTag(version?: string | null): string {
  if (!version) return 'V1';
  const s = String(version).toLowerCase();
  if (s.startsWith('v')) return s.toUpperCase();
  return `V${s.split('.')[0]}`;
}

/** Resolve the human-facing identity of a run: its ruleset, model and combine modes. */
export function describeRun(run: ModelRun | undefined, configs: PoolConfig[] | undefined) {
  const config = configs?.find((c) => c.id === run?.pool_config_id);
  const model = modelTag(run?.parameters?.model_version as string | undefined);
  return {
    config,
    rulesetName: config?.name ?? 'Unknown ruleset',
    model,
    modelLabel: MODEL_LABELS[model.toLowerCase()] ?? model,
  };
}

/** One-line, self-describing label for a run dropdown: "date · ruleset · model · status". */
export function runOptionLabel(run: ModelRun, configs: PoolConfig[] | undefined): string {
  const { rulesetName, model } = describeRun(run, configs);
  const when = format(new Date(run.started_at), 'MMM d HH:mm');
  return `${when}  ·  ${rulesetName}  ·  ${model}  ·  ${run.status}`;
}
