import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useSearchParams } from 'react-router-dom';
import { matchesApi } from '../api/matches';
import { oddsApi } from '../api/odds';
import { OddsMarketEditor } from '../components/OddsMarketEditor';
import { StatusBadge } from '../components/StatusBadge';
import { useToastContext } from '../components/Toast';
import { format } from 'date-fns';
import { RefreshCw } from 'lucide-react';

export default function OddsOverridesPage() {
  const { toast } = useToastContext();
  const qc = useQueryClient();
  const [searchParams] = useSearchParams();
  const initialMatchId = searchParams.get('match') ?? '';
  const [selectedMatchId, setSelectedMatchId] = useState(initialMatchId);

  const { data: matchesData, isLoading: matchesLoading } = useQuery({
    queryKey: ['matches', {}],
    queryFn: () => matchesApi.list({ page_size: 200 }),
  });

  const { data: matchOdds, isLoading: oddsLoading } = useQuery({
    queryKey: ['odds', 'match', selectedMatchId],
    queryFn: () => oddsApi.getMatchOdds(selectedMatchId),
    enabled: !!selectedMatchId,
  });

  const refreshOdds = useMutation({
    mutationFn: oddsApi.triggerRefresh,
    onSuccess: () => {
      toast.success('Odds refresh triggered');
      qc.invalidateQueries({ queryKey: ['odds'] });
    },
    onError: (e: Error) => toast.error(`Refresh failed: ${e.message}`),
  });

  const createOverride = useMutation({
    mutationFn: ({
      matchId,
      payload,
    }: {
      matchId: string;
      payload: Parameters<typeof oddsApi.createOverride>[1];
    }) => oddsApi.createOverride(matchId, payload),
    onSuccess: () => {
      toast.success('Override saved');
      qc.invalidateQueries({ queryKey: ['odds', 'match', selectedMatchId] });
      qc.invalidateQueries({ queryKey: ['matches'] });
    },
    onError: (e: Error) => toast.error(`Override failed: ${e.message}`),
  });

  const matches = matchesData?.items ?? [];
  const selectedMatch = matches.find((m) => m.id === selectedMatchId);

  const handleSaveOverride = async (
    matchId: string,
    marketKey: string,
    line: number | undefined,
    outcomeType: string,
    priceDecimal: number,
    reason?: string
  ) => {
    await createOverride.mutateAsync({
      matchId,
      payload: { market_key: marketKey, line, outcome_type: outcomeType, price_decimal: priceDecimal, reason },
    });
  };

  return (
    <div className="flex flex-col gap-5">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold text-slate-800">Odds & Overrides</h2>
          <p className="text-sm text-slate-500 mt-0.5">View market odds and apply manual overrides</p>
        </div>
        <button
          className="btn-secondary"
          onClick={() => refreshOdds.mutate()}
          disabled={refreshOdds.isPending}
        >
          <RefreshCw className={`w-4 h-4 ${refreshOdds.isPending ? 'animate-spin' : ''}`} />
          Refresh Odds
        </button>
      </div>

      {/* Match selector */}
      <div className="card p-4 flex flex-wrap items-center gap-4">
        <div className="flex flex-col gap-1 flex-1 min-w-[240px]">
          <label className="label">Select Match</label>
          <select
            className="input text-sm"
            value={selectedMatchId}
            onChange={(e) => setSelectedMatchId(e.target.value)}
            disabled={matchesLoading}
          >
            <option value="">— Select a match —</option>
            {matches.map((m) => (
              <option key={m.id} value={m.id}>
                {m.match_number ? `#${m.match_number} ` : ''}
                {m.home_team ?? m.home_placeholder ?? '?'} vs{' '}
                {m.away_team ?? m.away_placeholder ?? '?'}
                {m.kickoff_at ? ` (${format(new Date(m.kickoff_at), 'MMM d')})` : ''}
              </option>
            ))}
          </select>
        </div>
        {selectedMatch && (
          <div className="flex items-center gap-3">
            <StatusBadge status={selectedMatch.status} />
            {selectedMatch.has_odds && (
              <span className="text-xs text-green-700 bg-green-50 border border-green-200 rounded-full px-2 py-0.5">
                Has odds
              </span>
            )}
            {selectedMatch.has_overrides && (
              <span className="text-xs text-purple-700 bg-purple-50 border border-purple-200 rounded-full px-2 py-0.5">
                Has overrides
              </span>
            )}
          </div>
        )}
      </div>

      {/* Bookmaker Markets */}
      {selectedMatchId && oddsLoading && (
        <div className="card p-8 text-center text-slate-400">Loading odds...</div>
      )}

      {selectedMatchId && matchOdds && (
        <>
          {/* Consensus probabilities summary */}
          <div className="card p-4">
            <h3 className="text-sm font-semibold text-slate-700 mb-3">Consensus Probabilities</h3>
            <div className="flex flex-wrap gap-4 text-sm">
              {Object.entries(matchOdds.consensus_probabilities)
                .filter(([, v]) => v !== undefined)
                .map(([k, v]) => (
                  <div key={k} className="flex flex-col gap-0.5">
                    <span className="text-xs text-slate-500">{k.replace(/_/g, ' ')}</span>
                    <span className="font-mono font-semibold text-slate-800">
                      {((v as number) * 100).toFixed(1)}%
                    </span>
                  </div>
                ))}
            </div>
          </div>

          {/* Bookmaker odds table */}
          {matchOdds.bookmaker_markets.length > 0 && (
            <div className="card overflow-hidden">
              <div className="px-4 py-3 border-b border-slate-100">
                <h3 className="text-sm font-semibold text-slate-700">Bookmaker Markets</h3>
              </div>
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-slate-50 border-b border-slate-100">
                    <th className="px-4 py-2 text-left text-xs font-semibold text-slate-500">Bookmaker</th>
                    <th className="px-4 py-2 text-left text-xs font-semibold text-slate-500">Market</th>
                    <th className="px-4 py-2 text-left text-xs font-semibold text-slate-500">Line</th>
                    <th className="px-4 py-2 text-left text-xs font-semibold text-slate-500">Outcome</th>
                    <th className="px-4 py-2 text-right text-xs font-semibold text-slate-500">Decimal</th>
                    <th className="px-4 py-2 text-right text-xs font-semibold text-slate-500">Impl. Prob</th>
                  </tr>
                </thead>
                <tbody>
                  {matchOdds.bookmaker_markets.flatMap((bm, bi) =>
                    bm.outcomes.map((o, oi) => (
                      <tr
                        key={`${bi}-${oi}`}
                        className="border-b border-slate-50 hover:bg-slate-50/50"
                      >
                        <td className="px-4 py-2 text-xs text-slate-500">{bm.bookmaker_key ?? '—'}</td>
                        <td className="px-4 py-2 font-mono text-xs text-slate-600">{bm.market_key}</td>
                        <td className="px-4 py-2 font-mono text-xs text-slate-500">
                          {bm.line ?? '—'}
                        </td>
                        <td className="px-4 py-2 capitalize text-slate-700">{o.outcome_type}</td>
                        <td className="px-4 py-2 text-right font-mono text-slate-700">
                          {o.price_decimal.toFixed(2)}
                        </td>
                        <td className="px-4 py-2 text-right font-mono text-slate-500 text-xs">
                          {o.normalized_probability
                            ? (o.normalized_probability * 100).toFixed(1) + '%'
                            : o.price_decimal > 1
                            ? ((1 / o.price_decimal) * 100).toFixed(1) + '%'
                            : '—'}
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          )}

          {/* Override editor */}
          <div className="flex flex-col gap-2">
            <h3 className="text-sm font-semibold text-slate-700">Manual Overrides</h3>
            <OddsMarketEditor
              matchId={selectedMatchId}
              matchOdds={matchOdds}
              onSaveOverride={handleSaveOverride}
              loading={createOverride.isPending}
            />
          </div>
        </>
      )}

      {!selectedMatchId && (
        <div className="card p-10 flex flex-col items-center gap-3 text-center">
          <p className="text-slate-400 text-sm">Select a match above to view and edit odds.</p>
        </div>
      )}
    </div>
  );
}
