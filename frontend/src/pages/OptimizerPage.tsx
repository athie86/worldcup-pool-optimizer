import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Play, ChevronDown, ChevronRight, Activity, History, Sliders } from 'lucide-react';
import { poolConfigsApi } from '../api/poolConfigs';
import { oddsApi } from '../api/odds';
import { modelRunsApi } from '../api/modelRuns';
import type { Recommendation, MatchRecommendation } from '../types';
import { FitQualityBadge } from '../components/FitQualityBadge';
import { StatusBadge } from '../components/StatusBadge';
import { useToastContext } from '../components/Toast';
import { useNavigate } from 'react-router-dom';
import { format } from 'date-fns';
import { modelTag, describeRun, runOptionLabel } from '../lib/runLabels';

const STAGE_LABELS: Record<string, string> = {
  round_of_32: 'R32',
  round_of_16: 'R16',
  quarter_final: 'QF',
  semi_final: 'SF',
  final: 'F',
  third_place: '3rd',
};

function StageBadge({ stage }: { stage?: string }) {
  if (!stage || stage === 'group') return null;
  return (
    <span className="inline-block px-1.5 py-0.5 rounded text-[10px] font-bold bg-amber-100 text-amber-800 ml-1">
      {STAGE_LABELS[stage] ?? stage.toUpperCase()}
    </span>
  );
}

function RecommendationRow({ rec, isKnockout }: { rec: Recommendation; isKnockout?: boolean }) {
  return (
    <tr className="bg-blue-50/30 border-b border-blue-100">
      <td className="px-3 py-1.5 pl-8 text-xs text-slate-500">#{rec.rank}</td>
      <td colSpan={2} className="px-3 py-1.5 font-mono text-sm font-semibold text-slate-800">
        {rec.predicted_home_goals}–{rec.predicted_away_goals}
        {isKnockout && rec.penalties_winner && (
          <span className="ml-2 text-[10px] font-normal text-amber-700 bg-amber-50 px-1.5 py-0.5 rounded">
            {rec.predicted_advancer
              ? `${rec.predicted_advancer === 'home' ? 'Home' : 'Away'} advances on pens`
              : `Pen: ${rec.penalties_winner}`}
          </span>
        )}
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
      <td colSpan={3} />
    </tr>
  );
}

/** Mobile (stacked card) presentation of a single match's recommendations. */
function RecommendationCard({
  rec,
  expanded,
  onToggle,
  onDiag,
}: {
  rec: MatchRecommendation;
  expanded: boolean;
  onToggle: () => void;
  onDiag: () => void;
}) {
  const top = rec.recommendations[0];
  const isKnockout = !!rec.stage && rec.stage !== 'group';
  const cell = (label: string, value: React.ReactNode) => (
    <div className="flex flex-col">
      <span className="text-[10px] uppercase tracking-wide text-slate-400">{label}</span>
      <span className="font-mono text-sm text-slate-700">{value}</span>
    </div>
  );
  return (
    <div className="card p-4 flex flex-col gap-3">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <span className="font-semibold text-slate-800">
            {rec.home_team} vs {rec.away_team}
            <StageBadge stage={rec.stage} />
          </span>
          {rec.kickoff_at && (
            <div className="text-xs text-slate-400 font-mono">
              {format(new Date(rec.kickoff_at), 'MMM d HH:mm')}
            </div>
          )}
        </div>
        <FitQualityBadge status={rec.fit_status} />
      </div>

      {top ? (
        <div className="flex items-baseline gap-2">
          <span className="text-2xl font-mono font-bold text-slate-800">
            {top.predicted_home_goals}–{top.predicted_away_goals}
          </span>
          <span className="text-sm font-mono font-bold text-green-700">
            {top.expected_points.toFixed(3)} E[Pts]
          </span>
        </div>
      ) : (
        <span className="text-slate-300">—</span>
      )}

      <div className="grid grid-cols-2 gap-x-4 gap-y-2">
        {cell('λ H / A', `${rec.lambda_home?.toFixed(2) ?? '—'} / ${rec.lambda_away?.toFixed(2) ?? '—'}`)}
        {cell('P(0 pts)', top ? `${(top.zero_point_probability * 100).toFixed(1)}%` : '—')}
        {cell('Variance', top ? top.variance_points.toFixed(3) : '—')}
        {cell('Model', rec.model_version ? `v${rec.model_version.split('.')[0]}` : 'v1')}
      </div>

      <div className="flex items-center gap-2">
        {rec.recommendations.length > 1 && (
          <button
            className="flex-1 min-h-[40px] text-sm text-slate-700 bg-slate-100 hover:bg-slate-200 rounded-lg flex items-center justify-center gap-1.5"
            onClick={onToggle}
          >
            {expanded ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
            {expanded ? 'Hide' : `${rec.recommendations.length - 1} more`}
          </button>
        )}
        <button
          className="flex-1 min-h-[40px] text-sm text-blue-700 bg-blue-50 hover:bg-blue-100 rounded-lg flex items-center justify-center gap-1.5"
          onClick={onDiag}
        >
          <Activity className="w-4 h-4" />
          Diagnostics
        </button>
      </div>

      {expanded && rec.recommendations.length > 1 && (
        <div className="flex flex-col gap-1.5 border-t border-slate-100 pt-2">
          {rec.recommendations.slice(1).map((r) => (
            <div
              key={r.rank}
              className="flex items-center justify-between text-sm bg-blue-50/40 rounded-lg px-3 py-1.5"
            >
              <span className="font-mono font-semibold text-slate-700">
                #{r.rank} {r.predicted_home_goals}–{r.predicted_away_goals}
                {isKnockout && r.penalties_winner && (
                  <span className="ml-1 text-[10px] text-amber-700">(pens {r.penalties_winner})</span>
                )}
              </span>
              <span className="font-mono text-xs text-green-700">{r.expected_points.toFixed(3)}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default function OptimizerPage() {
  const { toast } = useToastContext();
  const qc = useQueryClient();
  const navigate = useNavigate();

  const [configId, setConfigId] = useState('');
  const [snapshotId, setSnapshotId] = useState('');
  const [topN, setTopN] = useState(3);
  const [modelVersion, setModelVersion] = useState('v2');
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
        model_version: modelVersion,
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
  const selectedConfig = configs?.find((c) => c.id === effectiveConfigId);

  // Most-recent first, so the dropdown reads top-down chronologically.
  const sortedRuns = [...(runs ?? [])].sort(
    (a, b) => new Date(b.started_at).getTime() - new Date(a.started_at).getTime(),
  );
  const viewedRun = runs?.find((r) => r.id === runId);
  const viewed = describeRun(viewedRun, configs);

  return (
    <div className="flex flex-col gap-5">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold text-slate-800">Optimizer</h2>
          <p className="text-sm text-slate-500 mt-0.5">Run the score-prediction model optimizer</p>
        </div>
      </div>

      {/* ── New run ─────────────────────────────────────────────────────── */}
      <div className="card p-5">
        <div className="flex items-center gap-2 mb-4">
          <Sliders className="w-4 h-4 text-slate-400" />
          <div>
            <h3 className="text-sm font-semibold text-slate-700">New optimizer run</h3>
            <p className="text-xs text-slate-500">
              Pick the scoring ruleset and model, then run. These settings only affect the
              run you start here.
            </p>
          </div>
        </div>

        <div className="flex flex-wrap items-end gap-4">
          <div className="flex flex-col gap-1 w-full sm:w-auto sm:min-w-[220px]">
            <label className="label">Scoring Ruleset</label>
            <select
              className="input text-sm"
              value={configId || effectiveConfigId}
              onChange={(e) => setConfigId(e.target.value)}
            >
              {configs?.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                  {c.active ? ' · active' : ''}
                </option>
              ))}
            </select>
          </div>

          <div className="flex flex-col gap-1 w-full sm:w-auto sm:min-w-[200px]">
            <label className="label">Prediction Model</label>
            <select
              className="input text-sm"
              value={modelVersion}
              onChange={(e) => setModelVersion(e.target.value)}
            >
              <option value="v2">V2 — Market-calibrated (full grid)</option>
              <option value="v1">V1 — Dixon-Coles (legacy)</option>
            </select>
          </div>

          <div className="flex flex-col gap-1 w-full sm:w-auto sm:min-w-[200px]">
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

          <div className="flex flex-col gap-1 w-full xs:w-24">
            <label className="label">Top N</label>
            <input
              type="number"
              className="input font-mono"
              min={1}
              max={10}
              value={topN}
              onChange={(e) => setTopN(parseInt(e.target.value) || 1)}
            />
          </div>

          <button
            className="btn-primary w-full sm:w-auto justify-center"
            onClick={() => runMutation.mutate()}
            disabled={runMutation.isPending}
          >
            <Play className="w-4 h-4" />
            {runMutation.isPending ? 'Running...' : 'Run Optimizer'}
          </button>
        </div>

        {/* What will run — makes the ruleset/model/combine-mode connection explicit */}
        {selectedConfig && (
          <div className="mt-4 px-4 py-3 rounded-xl bg-slate-50 border border-slate-200 flex flex-wrap items-center gap-2 text-sm text-slate-600">
            <span className="text-slate-400">Will run:</span>
            <span className="font-semibold text-slate-800">{selectedConfig.name}</span>
            <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-semibold bg-emerald-100 text-emerald-700">
              {modelTag(modelVersion)}
            </span>
            <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-semibold bg-sky-100 text-sky-700">
              Group: {selectedConfig.group_combine_mode === 'additive' ? 'Additive' : 'Best match'}
            </span>
            <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-semibold bg-violet-100 text-violet-700">
              Knockout: {selectedConfig.knockout_combine_mode === 'additive' ? 'Additive' : 'Best match'}
            </span>
            {selectedConfig.active && (
              <span className="text-xs text-emerald-600 font-medium">active</span>
            )}
          </div>
        )}
      </div>

      {/* ── Previous runs ───────────────────────────────────────────────── */}
      {sortedRuns.length > 0 && (
        <div className="card p-5">
          <div className="flex items-center gap-2 mb-4">
            <History className="w-4 h-4 text-slate-400" />
            <div>
              <h3 className="text-sm font-semibold text-slate-700">Previous runs</h3>
              <p className="text-xs text-slate-500">
                Each run is labelled with the ruleset and model it was executed under.
              </p>
            </div>
          </div>

          <div className="flex flex-col gap-1 max-w-xl">
            <label className="label">View run</label>
            <select
              className="input text-sm"
              value={runId}
              onChange={(e) => setRunId(e.target.value)}
            >
              <option value="">Select a run…</option>
              {sortedRuns.map((r) => (
                <option key={r.id} value={r.id}>
                  {runOptionLabel(r, configs)}
                </option>
              ))}
            </select>
          </div>

          {/* Viewed-run identity + status — derived from the run itself, not the
              new-run selectors above, so the table below is never mislabelled. */}
          {viewedRun && (
            <div className="mt-4 px-4 py-3 rounded-xl bg-slate-50 border border-slate-200 flex flex-col gap-2">
              <div className="flex flex-wrap items-center gap-2 text-sm">
                <span className="text-slate-400">Viewing:</span>
                <span className="font-semibold text-slate-800">{viewed.rulesetName}</span>
                <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-semibold bg-emerald-100 text-emerald-700">
                  {viewed.model}
                </span>
                {viewed.config && (
                  <>
                    <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-semibold bg-sky-100 text-sky-700">
                      Group: {viewed.config.group_combine_mode === 'additive' ? 'Additive' : 'Best match'}
                    </span>
                    <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-semibold bg-violet-100 text-violet-700">
                      Knockout: {viewed.config.knockout_combine_mode === 'additive' ? 'Additive' : 'Best match'}
                    </span>
                  </>
                )}
                {!viewed.config && (
                  <span className="text-[11px] text-amber-600">
                    ruleset no longer available
                  </span>
                )}
              </div>
              <div className="flex flex-wrap items-center gap-4 text-sm text-slate-600">
                <StatusBadge status={viewedRun.status} />
                <span>
                  Started: {format(new Date(viewedRun.started_at), 'MMM d, HH:mm:ss')}
                </span>
                {viewedRun.completed_at && (
                  <span>
                    Completed: {format(new Date(viewedRun.completed_at), 'HH:mm:ss')}
                  </span>
                )}
                {viewedRun.summary && (
                  <span>
                    {viewedRun.summary.optimized}/{viewedRun.summary.matches_total} optimized
                  </span>
                )}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Recommendations — mobile card list */}
      {runId && (
        <div className="lg:hidden flex flex-col gap-3">
          {recsLoading ? (
            <div className="card p-8 text-center text-slate-400">Loading recommendations...</div>
          ) : recommendations && recommendations.length > 0 ? (
            <>
              <h3 className="text-sm font-semibold text-slate-700">
                Recommendations ({recommendations.length} matches)
              </h3>
              {recommendations.map((rec) => (
                <RecommendationCard
                  key={rec.match_id}
                  rec={rec}
                  expanded={expandedRows.has(rec.match_id)}
                  onToggle={() => toggleExpand(rec.match_id)}
                  onDiag={() => navigate(`/diagnostics?match=${rec.match_id}&run=${runId}`)}
                />
              ))}
            </>
          ) : (
            <div className="card p-8 text-center text-slate-400">No recommendations yet</div>
          )}
        </div>
      )}

      {/* Recommendations Table — desktop */}
      {runId && (
        <div className="card overflow-hidden hidden lg:block">
          <div className="px-4 py-3 border-b border-slate-100">
            <h3 className="text-sm font-semibold text-slate-700">
              Recommendations {recommendations ? `(${recommendations.length} matches)` : ''}
            </h3>
          </div>
          {recsLoading ? (
            <div className="p-8 text-center text-slate-400">Loading recommendations...</div>
          ) : recommendations && recommendations.length > 0 ? (
            <div className="overflow-x-auto scroll-touch">
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
                    <th className="px-3 py-2.5 text-left text-xs font-semibold text-slate-500">Model</th>
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
                              <StageBadge stage={rec.stage} />
                            </span>
                            {rec.kickoff_at && (
                              <span className="text-xs text-slate-400 font-mono">
                                {format(new Date(rec.kickoff_at), 'MMM d HH:mm')}
                              </span>
                            )}
                            {rec.stage && rec.stage !== 'group' && rec.knockout_extras && (
                              <span className="text-[10px] text-slate-400 font-mono">
                                {rec.knockout_extras.p_goes_to_extra_time != null &&
                                  `ET ${(rec.knockout_extras.p_goes_to_extra_time * 100).toFixed(0)}%`}
                                {rec.knockout_extras.p_goes_to_penalties != null &&
                                  ` · Pens ${(rec.knockout_extras.p_goes_to_penalties * 100).toFixed(0)}%`}
                                {rec.knockout_extras.p_home_advances != null &&
                                  ` · Adv ${(rec.knockout_extras.p_home_advances * 100).toFixed(0)}/${((rec.knockout_extras.p_away_advances ?? (1 - rec.knockout_extras.p_home_advances)) * 100).toFixed(0)}`}
                              </span>
                            )}
                          </div>
                        </td>
                        <td className="px-3 py-2.5 font-mono text-xs text-slate-600">
                          {rec.lambda_home?.toFixed(3) ?? '—'} / {rec.lambda_away?.toFixed(3) ?? '—'}
                        </td>
                        <td className="px-3 py-2.5">
                          {rec.recommendations[0] ? (
                            <div className="flex flex-col gap-0.5">
                              <span className="font-mono font-bold text-slate-800">
                                {rec.recommendations[0].predicted_home_goals}–
                                {rec.recommendations[0].predicted_away_goals}
                              </span>
                              {rec.stage && rec.stage !== 'group' && rec.recommendations[0].penalties_winner && (
                                <span className="text-[10px] font-normal text-amber-700 bg-amber-50 px-1.5 py-0.5 rounded w-fit">
                                  {rec.recommendations[0].predicted_advancer
                                    ? `${rec.recommendations[0].predicted_advancer === 'home' ? 'Home' : 'Away'} advances on pens`
                                    : `Pen: ${rec.recommendations[0].penalties_winner}`}
                                </span>
                              )}
                            </div>
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
                          <div className="flex flex-col gap-0.5">
                            <span className="text-xs font-semibold text-slate-600">
                              {rec.model_version ? `v${rec.model_version.split('.')[0]}` : 'v1'}
                            </span>
                            {rec.fit_tier && (
                              <span className="text-[10px] font-mono text-slate-400">{rec.fit_tier}</span>
                            )}
                          </div>
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
                          <RecommendationRow
                            key={`${rec.match_id}-${r.rank}`}
                            rec={r}
                            isKnockout={!!rec.stage && rec.stage !== 'group'}
                          />
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
