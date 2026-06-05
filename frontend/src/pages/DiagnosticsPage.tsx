import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useSearchParams } from 'react-router-dom';
import { matchesApi } from '../api/matches';
import { modelRunsApi } from '../api/modelRuns';
import { DiagnosticsPanel } from '../components/DiagnosticsPanel';
import { format } from 'date-fns';

export default function DiagnosticsPage() {
  const [searchParams] = useSearchParams();
  const initialMatchId = searchParams.get('match') ?? '';
  const initialRunId = searchParams.get('run') ?? '';

  const [selectedMatchId, setSelectedMatchId] = useState(initialMatchId);
  const [selectedRunId, setSelectedRunId] = useState(initialRunId);

  const { data: matchesData, isLoading: matchesLoading } = useQuery({
    queryKey: ['matches', {}],
    queryFn: () => matchesApi.list({ page_size: 200 }),
  });

  const { data: runs, isLoading: runsLoading } = useQuery({
    queryKey: ['model-runs'],
    queryFn: modelRunsApi.list,
  });

  const { data: diagnostics, isLoading: diagLoading, error: diagError } = useQuery({
    queryKey: ['diagnostics', selectedRunId, selectedMatchId],
    queryFn: () => modelRunsApi.getDiagnostics(selectedRunId, selectedMatchId),
    enabled: !!selectedRunId && !!selectedMatchId,
  });

  const matches = matchesData?.items ?? [];
  const selectedMatch = matches.find((m) => m.id === selectedMatchId);

  return (
    <div className="flex flex-col gap-5">
      <div>
        <h2 className="text-xl font-bold text-slate-800">Diagnostics</h2>
        <p className="text-sm text-slate-500 mt-0.5">
          Inspect model calibration and heatmaps for a specific match
        </p>
      </div>

      {/* Selectors */}
      <div className="card p-4 flex flex-wrap items-end gap-4">
        <div className="flex flex-col gap-1 min-w-[240px] flex-1">
          <label className="label">Model Run</label>
          <select
            className="input text-sm"
            value={selectedRunId}
            onChange={(e) => setSelectedRunId(e.target.value)}
            disabled={runsLoading}
          >
            <option value="">— Select a run —</option>
            {runs?.map((r) => (
              <option key={r.id} value={r.id}>
                {format(new Date(r.started_at), 'MMM d, HH:mm')} — {r.status}
                {r.summary ? ` (${r.summary.optimized}/${r.summary.matches_total})` : ''}
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
          homeTeam={selectedMatch?.home_team ?? selectedMatch?.home_placeholder ?? 'Home'}
          awayTeam={selectedMatch?.away_team ?? selectedMatch?.away_placeholder ?? 'Away'}
        />
      )}

      {(!selectedMatchId || !selectedRunId) && (
        <div className="card p-10 flex flex-col items-center gap-3 text-center">
          <p className="text-slate-400 text-sm">
            Select a model run and match above to view diagnostics.
          </p>
        </div>
      )}
    </div>
  );
}
