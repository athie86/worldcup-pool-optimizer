import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Play, ChevronDown, ChevronRight, Activity } from 'lucide-react';
import { poolConfigsApi } from '../api/poolConfigs';
import { oddsApi } from '../api/odds';
import { modelRunsApi } from '../api/modelRuns';
import type { Recommendation } from '../types';
import { FitQualityBadge } from '../components/FitQualityBadge';
import { StatusBadge } from '../components/StatusBadge';
import { useToastContext } from '../components/Toast';
import { useNavigate } from 'react-router-dom';
import { format } from 'date-fns';

function RecommendationRow({ rec }: { rec: Recommendation }) {
  return (
    <tr className="bg-blue-50/30 border-b border-blue-100">
      <td className="px-3 py-1.5 pl-8 text-xs text-slate-500">#{rec.rank}</td>
      <td colSpan={2} className="px-3 py-1.5 font-mono text-sm font-semibold text-slate-800">
        {rec.predicted_home_goals}–{rec.predicted_away_goals}
      </td>
      <td className="px-3 py-1.5 font-mono text-sm text-green-700 font-semibold">
        {rec.expected_points.toFixed(3)}
      </td>
      <td className="px-3 py-1.5 font-mono text-xs text-slate-500">
        {(rec.zero_point_probability * 100).toFixed(1)}%
      </td>
      <td className="px-3 py-1.5 font-mono text-xs text-slate-500">
        {rec.variance_points.toFixed(3)}
      </td>
      <td className="px-3 py-1.5 font-mono text-xs text-slate-500">
        {(rec.score_probability * 100).toFixed(2)}%
      </td>
      <td colSpan={2} />
    </tr>
  );
}

export default function OptimizerPage() {
  const { toast } = useToastContext();
  const qc = useQueryClient();
  const navigate = useNavigate();

  const [configId, setConfigId] = useState('');
  const [snapshotId, setSnapshotId] = useState('');
  const [topN, setTopN] = useState(3);
  const [expandedRows, setExpandedRows] = useState<Set<string>>(new Set());
  const [runId, setRunId] = useState<string>('');

  const { data: configs } = useQuery({
    queryKey: ['pool-configs'],
    queryFn: poolConfigsApi.list,
  });

  const { data: snapshots } = useQuery({
    queryKey: ['odds', 'snapshots'],
    queryFn: oddsApi.listSnapshots,
  });

  const { data: runs } = useQuery({
    queryKey: ['model-runs'],
    queryFn: modelRunsApi.list,
  });

  const { data: recommendations, isLoading: recsLoading } = useQuery({
    queryKey: ['model-runs', runId, 'recommendations'],
    queryFn: () => modelRunsApi.getRecommendations(runId),
    enabled: !!runId,
  });

  const runMutation = useMutation({
    mutationFn: () =>
      modelRunsApi.run({
        pool_config_id: configId || (configs?.find((c) => c.active)?.id ?? configs?.[0]?.id ?? ''),
        odds_snapshot_id: snapshotId || undefined,
        top_n: topN,
      }),
    onSuccess: (run) => {
      toast.success('Optimizer run started');
      setRunId(run.id);
      qc.invalidateQueries({ queryKey: ['model-runs'] });
    },
    onError: (e: Error) => toast.error(`Run failed: ${e.message}`),
  });

  const toggleExpand = (matchId: string) => {
    setExpandedRows((prev) => {
      const next = new Set(prev);
      if (next.has(matchId)) next.delete(matchId);
      else next.add(matchId);
      return next;
    });
  };

  const activeConfig = configs?.find((c) => c.active) ?? configs?.[0];
  const effectiveConfigId = configId || activeConfig?.id || '';

  return (
    <div className="flex flex-col gap-5">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold text-slate-800">Optimizer</h2>
          <p className="text-sm text-slate-500 mt-0.5">Run the Poisson model optimizer</p>
        </div>
      </div>

      {/* Controls */}
      <div className="card p-5 flex flex-wrap items-end gap-4">
        <div className="flex flex-col gap-1 min-w-[180px]">
          <label className="label">Pool Configuration</label>
          <select
            className="input text-sm"
            value={configId || effectiveConfigId}
            onChange={(e) => setConfigId(e.target.value)}
          >
            {configs?.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name} {c.active ? '(active)' : ''}
              </option>
            ))}
          </select>
        </div>

        <div className="flex flex-col gap-1 min-w-[200px]">
          <label className="label">Odds Snapshot</label>
          <select
            className="input text-sm"
            value={snapshotId}
            onChange={(e) => setSnapshotId(e.target.value)}
          >
            <option value="">Latest snapshot</option>
            {snapshots?.map((s) => (
              <option key={s.id} value={s.id}>
                {format(new Date(s.fetched_at), 'MMM d HH:mm')} — {s.status}
              </option>
            ))}
          </select>
        </div>

        <div className="flex flex-col gap-1 w-24">
          <label className="label">Top N</label>
          <input
            type="number"
            className="input text-sm font-mono"
            min={1}
            max={10}
            value={topN}
            onChange={(e) => setTopN(parseInt(e.target.value) || 1)}
          />
        </div>

        <button
          className="btn-primary"
          onClick={() => runMutation.mutate()}
          disabled={runMutation.isPending}
        >
          <Play className="w-4 h-4" />
          {runMutation.isPending ? 'Running...' : 'Run Optimizer'}
        </button>

        {runs && runs.length > 0 && (
          <div className="flex flex-col gap-1 min-w-[200px]">
            <label className="label">View Run</label>
            <select
              className="input text-sm"
              value={runId}
              onChange={(e) => setRunId(e.target.value)}
            >
              <option value="">Select a run</option>
              {runs.map((r) => (
                <option key={r.id} value={r.id}>
                  {format(new Date(r.started_at), 'MMM d HH:mm')} — {r.status}
                </option>
              ))}
            </select>
          </div>
        )}
      </div>

      {/* Current Run Status */}
      {runId && runs && (
        <div className="card p-4 flex items-center gap-4">
          {(() => {
            const run = runs.find((r) => r.id === runId);
            if (!run) return null;
            return (
              <>
                <StatusBadge status={run.status} />
                <span className="text-sm text-slate-600">
                  Started: {format(new Date(run.started_at), 'MMM d, HH:mm:ss')}
                </span>
                {run.completed_at && (
                  <span className="text-sm text-slate-600">
                    Completed: {format(new Date(run.completed_at), 'HH:mm:ss')}
                  </span>
                )}
                {run.summary && (
                  <span className="text-sm text-slate-600">
                    {run.summary.optimized}/{run.summary.matches_total} optimized
                  </span>
                )}
              </>
            );
          })()}
        </div>
      )}

      {/* Recommendations Table */}
      {runId && (
        <div className="card overflow-hidden">
          <div className="px-4 py-3 border-b border-slate-100">
            <h3 className="text-sm font-semibold text-slate-700">
              Recommendations {recommendations ? `(${recommendations.length} matches)` : ''}
            </h3>
          </div>
          {recsLoading ? (
            <div className="p-8 text-center text-slate-400">Loading recommendations...</div>
          ) : recommendations && recommendations.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="w-full text-sm border-collapse">
                <thead>
                  <tr className="bg-slate-50 border-b border-slate-200">
                    <th className="px-3 py-2.5 w-8" />
                    <th className="px-3 py-2.5 text-left text-xs font-semibold text-slate-500">Match</th>
                    <th className="px-3 py-2.5 text-left text-xs font-semibold text-slate-500">λ H / A</th>
                    <th className="px-3 py-2.5 text-left text-xs font-semibold text-slate-500">Best Score</th>
                    <th className="px-3 py-2.5 text-left text-xs font-semibold text-slate-500">E[Pts]</th>
                    <th className="px-3 py-2.5 text-left text-xs font-semibold text-slate-500">P(0pts)</th>
                    <th className="px-3 py-2.5 text-left text-xs font-semibold text-slate-500">Variance</th>
                    <th className="px-3 py-2.5 text-left text-xs font-semibold text-slate-500">Fit</th>
                    <th className="px-3 py-2.5 w-16" />
                  </tr>
                </thead>
                <tbody>
                  {recommendations.map((rec, i) => (
                    <React.Fragment key={rec.match_id}>
                      <tr
                        className={`border-b border-slate-100 hover:bg-slate-50/70 ${
                          i % 2 === 0 ? 'bg-white' : 'bg-slate-50/30'
                        }`}
                      >
                        <td className="px-3 py-2.5">
                          {rec.recommendations.length > 1 && (
                            <button
                              className="text-slate-400 hover:text-slate-700"
                              onClick={() => toggleExpand(rec.match_id)}
                            >
                              {expandedRows.has(rec.match_id) ? (
                                <ChevronDown className="w-4 h-4" />
                              ) : (
                                <ChevronRight className="w-4 h-4" />
                              )}
                            </button>
                          )}
                        </td>
                        <td className="px-3 py-2.5">
                          <div className="flex flex-col gap-0.5">
                            <span className="font-medium text-slate-800">
                              {rec.home_team} vs {rec.away_team}
                            </span>
                            {rec.kickoff_at && (
                              <span className="text-xs text-slate-400 font-mono">
                                {format(new Date(rec.kickoff_at), 'MMM d HH:mm')}
                              </span>
                            )}
                          </div>
                        </td>
                        <td className="px-3 py-2.5 font-mono text-xs text-slate-600">
                          {rec.lambda_home?.toFixed(3) ?? '—'} / {rec.lambda_away?.toFixed(3) ?? '—'}
                        </td>
                        <td className="px-3 py-2.5">
                          {rec.recommendations[0] ? (
                            <span className="font-mono font-bold text-slate-800">
                              {rec.recommendations[0].predicted_home_goals}–
                              {rec.recommendations[0].predicted_away_goals}
                            </span>
                          ) : (
                            <span className="text-slate-300">—</span>
                          )}
                        </td>
                        <td className="px-3 py-2.5">
                          {rec.recommendations[0] ? (
                            <span className="font-mono font-bold text-green-700">
                              {rec.recommendations[0].expected_points.toFixed(3)}
                            </span>
                          ) : (
                            <span className="text-slate-300">—</span>
                          )}
                        </td>
                        <td className="px-3 py-2.5 font-mono text-sm text-slate-600">
                          {rec.recommendations[0]
                            ? (rec.recommendations[0].zero_point_probability * 100).toFixed(1) + '%'
                            : '—'}
                        </td>
                        <td className="px-3 py-2.5 font-mono text-sm text-slate-600">
                          {rec.recommendations[0]
                            ? rec.recommendations[0].variance_points.toFixed(3)
                            : '—'}
                        </td>
                        <td className="px-3 py-2.5">
                          <FitQualityBadge status={rec.fit_status} />
                        </td>
                        <td className="px-3 py-2.5">
                          <button
                            className="flex items-center gap-1 text-xs text-blue-600 hover:text-blue-800 px-2 py-1 rounded hover:bg-blue-50"
                            onClick={() =>
                              navigate(`/diagnostics?match=${rec.match_id}&run=${runId}`)
                            }
                          >
                            <Activity className="w-3 h-3" />
                            Diag
                          </button>
                        </td>
                      </tr>
                      {expandedRows.has(rec.match_id) &&
                        rec.recommendations.slice(1).map((r) => (
                          <RecommendationRow key={`${rec.match_id}-${r.rank}`} rec={r} />
                        ))}
                    </React.Fragment>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="p-8 text-center text-slate-400">No recommendations yet</div>
          )}
        </div>
      )}

      {!runId && (
        <div className="card p-10 flex flex-col items-center gap-3 text-center">
          <Play className="w-10 h-10 text-slate-200" />
          <p className="text-slate-400 text-sm">
            Select a pool configuration and run the optimizer to see recommendations.
          </p>
        </div>
      )}
    </div>
  );
}
