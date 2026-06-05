import { useState } from 'react';
import { Save } from 'lucide-react';
import type { MatchOdds, ManualOverride } from '../types';

interface OddsMarketEditorProps {
  matchId: string;
  matchOdds: MatchOdds | null;
  onSaveOverride: (
    matchId: string,
    marketKey: string,
    line: number | undefined,
    outcomeType: string,
    priceDecimal: number,
    reason?: string
  ) => Promise<void>;
  loading?: boolean;
}

interface OverrideField {
  market_key: string;
  line?: number;
  outcome_type: string;
  value: string;
  reason: string;
}

const OUTCOME_LABELS: Record<string, string> = {
  home: 'Home Win',
  draw: 'Draw',
  away: 'Away Win',
  over: 'Over',
  under: 'Under',
};

function impliedProb(decimal: number): string {
  if (!decimal || decimal <= 1) return '—';
  return ((1 / decimal) * 100).toFixed(1) + '%';
}

function decimalToDisplayProb(p: number | undefined): string {
  if (p === undefined) return '—';
  return (p * 100).toFixed(1) + '%';
}

export function OddsMarketEditor({
  matchId,
  matchOdds,
  onSaveOverride,
  loading,
}: OddsMarketEditorProps) {
  const [overrides, setOverrides] = useState<Record<string, OverrideField>>({});
  const [saving, setSaving] = useState<Record<string, boolean>>({});

  const getKey = (marketKey: string, line: number | undefined, outcomeType: string) =>
    `${marketKey}:${line ?? ''}:${outcomeType}`;

  const getExistingOverride = (
    marketKey: string,
    line: number | undefined,
    outcomeType: string
  ): ManualOverride | undefined =>
    matchOdds?.overrides.find(
      (o) =>
        o.market_key === marketKey &&
        o.line === line &&
        o.outcome_type === outcomeType &&
        o.enabled
    );

  const handleChange = (
    marketKey: string,
    line: number | undefined,
    outcomeType: string,
    field: 'value' | 'reason',
    val: string
  ) => {
    const k = getKey(marketKey, line, outcomeType);
    setOverrides((prev) => ({
      ...prev,
      [k]: {
        market_key: marketKey,
        line,
        outcome_type: outcomeType,
        value: field === 'value' ? val : (prev[k]?.value ?? ''),
        reason: field === 'reason' ? val : (prev[k]?.reason ?? ''),
      },
    }));
  };

  const handleSave = async (
    marketKey: string,
    line: number | undefined,
    outcomeType: string
  ) => {
    const k = getKey(marketKey, line, outcomeType);
    const field = overrides[k];
    if (!field) return;
    const price = parseFloat(field.value);
    if (isNaN(price) || price <= 1) return;
    setSaving((prev) => ({ ...prev, [k]: true }));
    try {
      await onSaveOverride(matchId, marketKey, line, outcomeType, price, field.reason || undefined);
    } finally {
      setSaving((prev) => ({ ...prev, [k]: false }));
    }
  };

  const consensus = matchOdds?.consensus_probabilities ?? {};

  const h2hOutcomes = [
    { outcomeType: 'home', consensus: consensus.home_win },
    { outcomeType: 'draw', consensus: consensus.draw },
    { outcomeType: 'away', consensus: consensus.away_win },
  ];

  const totalsLines = [1.5, 2.5, 3.5];
  const totalsOutcomeMap: Record<number, { over?: number; under?: number }> = {
    1.5: { over: consensus.over_1_5, under: consensus.under_1_5 },
    2.5: { over: consensus.over_2_5, under: consensus.under_2_5 },
    3.5: { over: consensus.over_3_5, under: consensus.under_3_5 },
  };

  return (
    <div className="flex flex-col gap-6">
      {/* H2H */}
      <div className="card overflow-hidden">
        <div className="px-4 py-3 border-b border-slate-100 bg-slate-50">
          <h4 className="text-sm font-semibold text-slate-700">Match Result (1X2)</h4>
        </div>
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-slate-100">
              <th className="px-4 py-2 text-left text-xs text-slate-500 font-medium">Outcome</th>
              <th className="px-4 py-2 text-right text-xs text-slate-500 font-medium">Consensus Prob</th>
              <th className="px-4 py-2 text-right text-xs text-slate-500 font-medium">Current Override</th>
              <th className="px-4 py-2 text-left text-xs text-slate-500 font-medium">Override (Decimal)</th>
              <th className="px-4 py-2 text-left text-xs text-slate-500 font-medium">Reason</th>
              <th className="px-4 py-2 w-10" />
            </tr>
          </thead>
          <tbody>
            {h2hOutcomes.map(({ outcomeType, consensus: cp }) => {
              const k = getKey('h2h', undefined, outcomeType);
              const existing = getExistingOverride('h2h', undefined, outcomeType);
              const field = overrides[k];
              return (
                <tr key={outcomeType} className="border-b border-slate-50 hover:bg-slate-50/50">
                  <td className="px-4 py-2.5 font-medium text-slate-700">
                    {OUTCOME_LABELS[outcomeType]}
                  </td>
                  <td className="px-4 py-2.5 text-right font-mono text-slate-600">
                    {decimalToDisplayProb(cp)}
                  </td>
                  <td className="px-4 py-2.5 text-right font-mono text-slate-500 text-xs">
                    {existing
                      ? `${existing.price_decimal.toFixed(2)} (${impliedProb(existing.price_decimal)})`
                      : '—'}
                  </td>
                  <td className="px-4 py-2.5">
                    <input
                      className="input w-24 font-mono text-sm"
                      type="number"
                      min="1.01"
                      step="0.01"
                      placeholder="e.g. 2.10"
                      value={field?.value ?? ''}
                      onChange={(e) =>
                        handleChange('h2h', undefined, outcomeType, 'value', e.target.value)
                      }
                    />
                    {field?.value && parseFloat(field.value) > 1 && (
                      <span className="ml-2 text-xs text-slate-400 font-mono">
                        → {impliedProb(parseFloat(field.value))}
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-2.5">
                    <input
                      className="input text-sm"
                      placeholder="Optional reason"
                      value={field?.reason ?? ''}
                      onChange={(e) =>
                        handleChange('h2h', undefined, outcomeType, 'reason', e.target.value)
                      }
                    />
                  </td>
                  <td className="px-4 py-2.5">
                    <button
                      className="btn-primary px-2 py-1 text-xs"
                      disabled={!field?.value || loading || saving[k]}
                      onClick={() => handleSave('h2h', undefined, outcomeType)}
                    >
                      <Save className="w-3.5 h-3.5" />
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Totals */}
      <div className="card overflow-hidden">
        <div className="px-4 py-3 border-b border-slate-100 bg-slate-50">
          <h4 className="text-sm font-semibold text-slate-700">Totals (Over/Under)</h4>
        </div>
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-slate-100">
              <th className="px-4 py-2 text-left text-xs text-slate-500 font-medium">Line</th>
              <th className="px-4 py-2 text-left text-xs text-slate-500 font-medium">Outcome</th>
              <th className="px-4 py-2 text-right text-xs text-slate-500 font-medium">Consensus Prob</th>
              <th className="px-4 py-2 text-right text-xs text-slate-500 font-medium">Current Override</th>
              <th className="px-4 py-2 text-left text-xs text-slate-500 font-medium">Override (Decimal)</th>
              <th className="px-4 py-2 text-left text-xs text-slate-500 font-medium">Reason</th>
              <th className="px-4 py-2 w-10" />
            </tr>
          </thead>
          <tbody>
            {totalsLines.flatMap((line) =>
              (['over', 'under'] as const).map((outcomeType) => {
                const cp = totalsOutcomeMap[line]?.[outcomeType];
                const k = getKey('totals', line, outcomeType);
                const existing = getExistingOverride('totals', line, outcomeType);
                const field = overrides[k];
                return (
                  <tr key={k} className="border-b border-slate-50 hover:bg-slate-50/50">
                    <td className="px-4 py-2.5 font-mono text-slate-600">{line}</td>
                    <td className="px-4 py-2.5 font-medium text-slate-700 capitalize">{outcomeType}</td>
                    <td className="px-4 py-2.5 text-right font-mono text-slate-600">
                      {decimalToDisplayProb(cp)}
                    </td>
                    <td className="px-4 py-2.5 text-right font-mono text-slate-500 text-xs">
                      {existing
                        ? `${existing.price_decimal.toFixed(2)} (${impliedProb(existing.price_decimal)})`
                        : '—'}
                    </td>
                    <td className="px-4 py-2.5">
                      <input
                        className="input w-24 font-mono text-sm"
                        type="number"
                        min="1.01"
                        step="0.01"
                        placeholder="e.g. 1.85"
                        value={field?.value ?? ''}
                        onChange={(e) =>
                          handleChange('totals', line, outcomeType, 'value', e.target.value)
                        }
                      />
                      {field?.value && parseFloat(field.value) > 1 && (
                        <span className="ml-2 text-xs text-slate-400 font-mono">
                          → {impliedProb(parseFloat(field.value))}
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-2.5">
                      <input
                        className="input text-sm"
                        placeholder="Optional reason"
                        value={field?.reason ?? ''}
                        onChange={(e) =>
                          handleChange('totals', line, outcomeType, 'reason', e.target.value)
                        }
                      />
                    </td>
                    <td className="px-4 py-2.5">
                      <button
                        className="btn-primary px-2 py-1 text-xs"
                        disabled={!field?.value || loading || saving[k]}
                        onClick={() => handleSave('totals', line, outcomeType)}
                      >
                        <Save className="w-3.5 h-3.5" />
                      </button>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
