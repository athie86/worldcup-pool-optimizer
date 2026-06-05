import { useState } from 'react';
import { AlertTriangle, ToggleLeft, ToggleRight } from 'lucide-react';
import type { ScoringRule } from '../types';

interface EditableScoringTableProps {
  rules: ScoringRule[];
  onChange: (ruleId: string, changes: { points?: number; enabled?: boolean }) => void;
  loading?: boolean;
}

export function EditableScoringTable({ rules, onChange, loading }: EditableScoringTableProps) {
  const [localChanges, setLocalChanges] = useState<Record<string, { points?: number; enabled?: boolean }>>({});

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

  // Warnings
  const activeRules = rules.filter((r) => getRule(r).enabled);
  const hasDrawRule = activeRules.some((r) => r.code.includes('draw') || r.code.includes('correct_draw'));
  const hasCatchAll = activeRules.some(
    (r) => r.code.includes('wrong_result') || r.code.includes('zero') || r.code.includes('no_points')
  );

  const sortedRules = [...rules].sort((a, b) => a.display_specificity_rank - b.display_specificity_rank);

  return (
    <div className="flex flex-col gap-3">
      {/* Warnings */}
      {(!hasDrawRule || !hasCatchAll) && (
        <div className="bg-amber-50 border border-amber-200 rounded-xl p-3 flex flex-col gap-1">
          <div className="flex items-center gap-2 text-sm font-semibold text-amber-800">
            <AlertTriangle className="w-4 h-4 shrink-0" />
            Scoring rule warnings
          </div>
          {!hasDrawRule && (
            <p className="text-xs text-amber-700 ml-6">
              No draw-specific rule is enabled. Draws may not award correct points.
            </p>
          )}
          {!hasCatchAll && (
            <p className="text-xs text-amber-700 ml-6">
              No catch-all / wrong-result rule is enabled. Wrong predictions may score 0 unexpectedly.
            </p>
          )}
        </div>
      )}

      <div className="card overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-slate-50 border-b border-slate-200">
              <th className="px-4 py-2.5 text-left text-xs font-semibold text-slate-500 w-16">On</th>
              <th className="px-4 py-2.5 text-left text-xs font-semibold text-slate-500">Rule</th>
              <th className="px-4 py-2.5 text-left text-xs font-semibold text-slate-500 hidden md:table-cell">
                Description
              </th>
              <th className="px-4 py-2.5 text-right text-xs font-semibold text-slate-500 w-28">Points</th>
            </tr>
          </thead>
          <tbody>
            {sortedRules.map((rawRule, i) => {
              const rule = getRule(rawRule);
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
                      <span className="font-medium text-slate-800">{rule.label}</span>
                      <span className="text-xs font-mono text-slate-400">{rule.code}</span>
                    </div>
                  </td>
                  <td className="px-4 py-2.5 hidden md:table-cell">
                    <span className="text-xs text-slate-500">{rawRule.description ?? '—'}</span>
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
