import { useEffect, useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useSearchParams } from 'react-router-dom';
import { matchesApi } from '../api/matches';
import { modelRunsApi } from '../api/modelRuns';
import { poolConfigsApi } from '../api/poolConfigs';
import { DiagnosticsPanel } from '../components/DiagnosticsPanel';
import { StatusBadge } from '../components/StatusBadge';
import { describeRun, runOptionLabel } from '../lib/runLabels';
import { format } from 'date-fns';

export default function DiagnosticsPage() {
  const [searchParams] = useSearchParams();
  const initialMatchId = searchParams.get('match') ?? '';
  const initialRunId = searchParams.get('run') ?? '';

  const [selectedMatchId, setSelectedMatchId] = useState(initialMatchId);
  const [selectedRunId, setSelectedRunId] = useState(initialRunId);

  const { data: matchesData } = useQuery({
    queryKey: ['matches', {}],
    queryFn: () => matchesApi.list({ page_size: 200 }),
  });

  const { data: runs, isLoading: runsLoading } = useQuery({
    queryKey: ['model-runs'],
    queryFn: modelRunsApi.list,
  });

  const { data: configs } = useQuery({
    queryKey: ['pool-configs'],
    queryFn: poolConfigsApi.list,
  });

  // Recommendations for the chosen run tell us exactly which matches that run
  // produced a model fit for — the match picker is scoped to these so you can
  // never select a match the run never computed (the old "No model fit" error).
  const { data: runRecommendations, isLoading: recsLoading } = useQuery({
    queryKey: ['model-runs', selectedRunId, 'recommendations'],
    queryFn: () => modelRunsApi.getRecommendations(selectedRunId),
    enabled: !!selectedRunId,
  });

  const { data: diagnostics, isLoading: diagLoading, error: diagError } = useQuery({
    queryKey: ['diagnostics', selectedRunId, selectedMatchId],
    queryFn: () => modelRunsApi.getDiagnostics(selectedRunId, selectedMatchId),
    enabled: !!selectedRunId && !!selectedMatchId,
  });

  const matches = matchesData?.items ?? [];

  // Match metadata (number, kickoff) for the matches in this run, preserving the
  // run's recommendation order; fall back to recommendation team names.
  const availableMatches = useMemo(() => {
    if (!runRecommendations) return [];
    return runRecommendations.map((rec) => {
      const meta = matches.find((m) => m.id === rec.match_id);
      return {
        id: rec.match_id,
        match_number: meta?.match_number,
        home: meta?.home_team ?? meta?.home_placeholder ?? rec.home_team ?? '?',
        away: meta?.away_team ?? meta?.away_placeholder ?? rec.away_team ?? '?',
        kickoff_at: meta?.kickoff_at ?? rec.kickoff_at,
      };
    });
  }, [runRecommendations, matches]);

  // If the selected match isn't part of the chosen run, drop it so we don't fire
  // a diagnostics request that can only fail.
  useEffect(() => {
    if (!runRecommendations || !selectedMatchId) return;
    if (!runRecommendations.some((rec) => rec.match_id === selectedMatchId)) {
      setSelectedMatchId('');
    }
  }, [runRecommendations, selectedMatchId]);

  const selectedMatch = availableMatches.find((m) => m.id === selectedMatchId);
  const viewedRun = runs?.find((r) => r.id === selectedRunId);
  const viewed = describeRun(viewedRun, configs);

  // Newest-first, matching the Optimizer page ordering.
  const sortedRuns = [...(runs ?? [])].sort(
    (a, b) => new Date(b.started_at).getTime() - new Date(a.started_at).getTime(),
  );

  return (
    <div className="flex flex-col gap-5">
      <div>
        <h2 className="text-xl font-bold text-slate-800">Diagnostics</h2>
        <p className="text-sm text-slate-500 mt-0.5">
          Inspect model calibration and heatmaps for a specific match
        </p>
      </div>

      {/* Selectors */}
      <div className="card p-4 flex flex-col gap-4">
        <div className="flex flex-wrap items-end gap-4">
          <div className="flex flex-col gap-1 min-w-[280px] flex-1">
            <label className="label">Model Run</label>
            <select
              className="input text-sm"
              value={selectedRunId}
              onChange={(e) => {
                setSelectedRunId(e.target.value);
                setSelectedMatchId('');
              }}
              disabled={runsLoading}
            >
              <option value="">— Select a run —</option>
              {sortedRuns.map((r) => (
                <option key={r.id} value={r.id}>
                  {runOptionLabel(r, configs)}
                  {r.summary ? `  ·  ${r.summary.optimized}/${r.summary.matches_total}` : ''}
                </option>
              ))}
            </select>
          </div>
          <div className="flex flex-col gap-1 min-w-[280px] flex-1">
            <label className="label">Match</label>
            <select
              className="input text-sm"
              value={selectedMatchId}
              onChange={(e) => setSelectedMatchId(e.target.value)}
              disabled={!selectedRunId || recsLoading}
            >
              <option value="">
                {!selectedRunId
                  ? '— Select a run first —'
                  : recsLoading
                    ? 'Loading run matches…'
                    : availableMatches.length === 0
                      ? 'No matches in this run'
                      : '— Select a match —'}
              </option>
              {availableMatches.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.match_number ? `#${m.match_number} ` : ''}
                  {m.home} vs {m.away}
                  {m.kickoff_at ? ` (${format(new Date(m.kickoff_at), 'MMM d')})` : ''}
                </option>
              ))}
            </select>
          </div>
        </div>

        {/* Identity of the run being inspected — same vocabulary as the Optimizer page. */}
        {viewedRun && (
          <div className="px-4 py-3 rounded-xl bg-slate-50 border border-slate-200 flex flex-wrap items-center gap-2 text-sm text-slate-600">
            <span className="text-slate-400">Inspecting:</span>
            <span className="font-semibold text-slate-800">{viewed.rulesetName}</span>
            <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-semibold bg-emerald-100 text-emerald-700">
              {viewed.model}
            </span>
            <StatusBadge status={viewedRun.status} />
            <span className="text-xs text-slate-400">
              {format(new Date(viewedRun.started_at), 'MMM d, HH:mm:ss')}
            </span>
            {availableMatches.length > 0 && (
              <span className="text-xs text-slate-400">
                · {availableMatches.length} matches with a model fit
              </span>
            )}
          </div>
        )}
      </div>

      {/* Diagnostics */}
      {selectedMatchId && selectedRunId && diagLoading && (
        <div className="card p-8 text-center text-slate-400">Loading diagnostics...</div>
      )}

      {diagError && (
        <div className="card p-6 bg-red-50 border-red-200 text-red-700 text-sm">
          Failed to load diagnostics:{' '}
          {diagError instanceof Error ? diagError.message : 'Unknown error'}
        </div>
      )}

      {diagnostics && (
        <DiagnosticsPanel
          diagnostics={diagnostics}
          homeTeam={selectedMatch?.home ?? 'Home'}
          awayTeam={selectedMatch?.away ?? 'Away'}
        />
      )}

      {(!selectedMatchId || !selectedRunId) && (
        <div className="card p-10 flex flex-col items-center gap-3 text-center">
          <p className="text-slate-400 text-sm">
            {!selectedRunId
              ? 'Select a model run above, then pick one of its matches to view diagnostics.'
              : 'Select a match from this run to view diagnostics.'}
          </p>
        </div>
      )}
    </div>
  );
}
