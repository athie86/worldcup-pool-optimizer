import { useState } from 'react';
import { Info, ToggleLeft, ToggleRight } from 'lucide-react';
import type { ScoringRule, CombineMode } from '../types';

interface RuleChange {
  points?: number;
  enabled?: boolean;
  config?: Record<string, unknown> | null;
}

interface EditableScoringTableProps {
  rules: ScoringRule[];
  onChange: (ruleId: string, changes: RuleChange) => void;
  loading?: boolean;
  combineMode?: CombineMode;
}

/** Hover/focus tooltip showing what a component means, with an example. */
function RuleTooltip({ rule }: { rule: ScoringRule }) {
  return (
    <span className="relative inline-flex group align-middle">
      <button
        type="button"
        tabIndex={0}
        aria-label={`What does "${rule.label}" mean?`}
        className="text-slate-300 hover:text-red-700 focus:text-red-700 focus:outline-none"
      >
        <Info className="w-4 h-4" />
      </button>
      <span
        role="tooltip"
        className="pointer-events-none absolute left-1/2 z-20 hidden w-64 -translate-x-1/2 translate-y-2 rounded-lg bg-slate-800 px-3 py-2 text-left text-xs text-white shadow-lg group-hover:block group-focus-within:block top-full"
      >
        <span className="block font-semibold text-white">{rule.label}</span>
        {rule.description && (
          <span className="mt-1 block text-slate-200">{rule.description}</span>
        )}
        {rule.example && (
          <span className="mt-1 block italic text-amber-200">e.g. {rule.example}</span>
        )}
      </span>
    </span>
  );
}

export function EditableScoringTable({
  rules,
  onChange,
  loading,
  combineMode = 'best',
}: EditableScoringTableProps) {
  const [localChanges, setLocalChanges] = useState<Record<string, RuleChange>>({});

  const getRule = (rule: ScoringRule) => ({
    ...rule,
    ...(localChanges[rule.id] ?? {}),
  });

  const handlePoints = (ruleId: string, value: string) => {
    const num = parseFloat(value);
    if (isNaN(num)) return;
    setLocalChanges((prev) => ({ ...prev, [ruleId]: { ...prev[ruleId], points: num } }));
  };

  const handleToggle = (rule: ScoringRule) => {
    const current = getRule(rule);
    const next = !current.enabled;
    setLocalChanges((prev) => ({ ...prev, [rule.id]: { ...prev[rule.id], enabled: next } }));
    onChange(rule.id, { enabled: next });
  };

  const handlePointsBlur = (ruleId: string) => {
    const change = localChanges[ruleId];
    if (change?.points !== undefined) {
      onChange(ruleId, { points: change.points });
    }
  };

  const handleBucketCap = (rule: ScoringRule, value: string) => {
    const trimmed = value.trim();
    const config =
      trimmed === ''
        ? null
        : { ...(rule.config ?? {}), bucket_cap: parseInt(trimmed, 10) };
    setLocalChanges((prev) => ({ ...prev, [rule.id]: { ...prev[rule.id], config } }));
    onChange(rule.id, { config });
  };

  const sortedRules = [...rules].sort(
    (a, b) => a.display_specificity_rank - b.display_specificity_rank
  );

  return (
    <div className="flex flex-col gap-3">
      <p className="text-xs text-slate-500">
        {combineMode === 'additive' ? (
          <>
            <strong>Additive:</strong> every enabled component that matches is summed.
            Hover the <Info className="inline w-3 h-3 -mt-0.5" /> on any row to see what it
            means.
          </>
        ) : (
          <>
            <strong>Best match:</strong> only the single highest-value matching component
            is awarded. Hover the <Info className="inline w-3 h-3 -mt-0.5" /> on any row to
            see what it means.
          </>
        )}
      </p>

      <div className="card overflow-visible">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-slate-50 border-b border-slate-200">
              <th className="px-4 py-2.5 text-left text-xs font-semibold text-slate-500 w-16">On</th>
              <th className="px-4 py-2.5 text-left text-xs font-semibold text-slate-500">Rule</th>
              <th className="px-4 py-2.5 text-left text-xs font-semibold text-slate-500 hidden md:table-cell">
                Example
              </th>
              <th className="px-4 py-2.5 text-right text-xs font-semibold text-slate-500 w-28">Points</th>
            </tr>
          </thead>
          <tbody>
            {sortedRules.map((rawRule, i) => {
              const rule = getRule(rawRule);
              const bucketCap =
                (rule.config && (rule.config as Record<string, unknown>).bucket_cap) ?? '';
              return (
                <tr
                  key={rule.id}
                  className={`border-b border-slate-100 transition-colors ${
                    !rule.enabled ? 'opacity-50' : ''
                  } ${i % 2 === 0 ? 'bg-white' : 'bg-slate-50/30'}`}
                >
                  <td className="px-4 py-2.5">
                    <button
                      onClick={() => handleToggle(rawRule)}
                      disabled={loading}
                      className="text-slate-400 hover:text-red-700 transition-colors"
                      title={rule.enabled ? 'Disable rule' : 'Enable rule'}
                    >
                      {rule.enabled ? (
                        <ToggleRight className="w-6 h-6 text-green-600" />
                      ) : (
                        <ToggleLeft className="w-6 h-6 text-slate-300" />
                      )}
                    </button>
                  </td>
                  <td className="px-4 py-2.5">
                    <div className="flex flex-col gap-0.5">
                      <span className="flex items-center gap-1.5 font-medium text-slate-800">
                        {rule.label}
                        <RuleTooltip rule={rawRule} />
                      </span>
                      <span className="text-xs font-mono text-slate-400">{rule.code}</span>
                      {rule.code === 'total_goals' && (
                        <label className="mt-1 flex items-center gap-1.5 text-[11px] text-slate-500">
                          Bucket cap
                          <input
                            type="number"
                            min={1}
                            placeholder="none"
                            className="w-16 text-right input !py-0.5 font-mono text-xs"
                            value={bucketCap as number | string}
                            disabled={loading || !rule.enabled}
                            onChange={(e) => handleBucketCap(rawRule, e.target.value)}
                            title="Totals at or above this value share one bucket (e.g. 4 means 4+). Leave blank for exact total."
                          />
                          <span className="text-slate-400">(e.g. 4 → 4+)</span>
                        </label>
                      )}
                    </div>
                  </td>
                  <td className="px-4 py-2.5 hidden md:table-cell">
                    <span className="text-xs italic text-slate-500">
                      {rawRule.example ?? '—'}
                    </span>
                  </td>
                  <td className="px-4 py-2.5 text-right">
                    <input
                      type="number"
                      className="w-20 text-right input font-mono text-sm"
                      value={rule.points}
                      step="0.5"
                      disabled={loading || !rule.enabled}
                      onChange={(e) => handlePoints(rule.id, e.target.value)}
                      onBlur={() => handlePointsBlur(rule.id)}
                    />
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
