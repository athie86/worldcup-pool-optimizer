import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  RefreshCw,
  Play,
  Download,
  Clock,
  CheckCircle,
  AlertTriangle,
  GitBranch,
  Zap,
} from 'lucide-react';
import { matchesApi } from '../api/matches';
import { oddsApi } from '../api/odds';
import { modelRunsApi } from '../api/modelRuns';
import { exportsApi } from '../api/exports';
import { poolConfigsApi } from '../api/poolConfigs';
import { MetricCard } from '../components/MetricCard';
import { StatusBadge } from '../components/StatusBadge';
import { useToastContext } from '../components/Toast';
import { format } from 'date-fns';

export default function DashboardPage() {
  const { toast } = useToastContext();
  const qc = useQueryClient();

  const { data: stats, isLoading } = useQuery({
    queryKey: ['dashboard', 'stats'],
    queryFn: matchesApi.dashboardStats,
    refetchInterval: 30_000,
  });

  const { data: poolConfigs } = useQuery({
    queryKey: ['pool-configs'],
    queryFn: poolConfigsApi.list,
  });

  const activeConfig = poolConfigs?.find((c) => c.active) ?? poolConfigs?.[0];

  const refreshOdds = useMutation({
    mutationFn: oddsApi.triggerRefresh,
    onSuccess: (result) => {
      qc.invalidateQueries({ queryKey: ['dashboard'] });
      qc.invalidateQueries({ queryKey: ['odds'] });
      if (result.status === 'error') {
        toast.error(result.message ?? 'Odds refresh failed');
      } else {
        toast.success(`Odds refreshed — ${result.events_count} event(s) fetched`);
      }
    },
    onError: (e: Error) => toast.error(`Refresh failed: ${e.message}`),
  });

  const runOptimizer = useMutation({
    mutationFn: () =>
      modelRunsApi.run({
        pool_config_id: activeConfig?.id ?? '',
      }),
    onSuccess: () => {
      toast.success('Optimizer run started');
      qc.invalidateQueries({ queryKey: ['model-runs'] });
      qc.invalidateQueries({ queryKey: ['dashboard'] });
    },
    onError: (e: Error) => toast.error(`Optimizer failed: ${e.message}`),
  });

  const exportData = useMutation({
    mutationFn: () => {
      const runId = stats?.latest_model_run?.id;
      if (!runId) throw new Error('No model run available. Run the optimizer first.');
      return exportsApi.create({
        format: 'xlsx',
        model_run_id: runId,
      });
    },
    onSuccess: (record) => {
      toast.success('Export created');
      window.open(exportsApi.download(record.id), '_blank');
    },
    onError: (e: Error) => toast.error(`Export failed: ${e.message}`),
  });

  const latestRun = stats?.latest_model_run;

  const fitStatus = stats?.avg_fit_quality ?? 'pending';
  const fitStatusColor =
    fitStatus === 'good' ? 'good' : fitStatus === 'acceptable' ? 'warning' : 'danger';

  return (
    <div className="flex flex-col gap-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold text-slate-800">Dashboard</h2>
          <p className="text-sm text-slate-500 mt-0.5">World Cup 2026 Pool Optimizer</p>
        </div>
        <div className="flex items-center gap-2">
          <button
            className="btn-secondary"
            onClick={() => refreshOdds.mutate()}
            disabled={refreshOdds.isPending}
          >
            <RefreshCw className={`w-4 h-4 ${refreshOdds.isPending ? 'animate-spin' : ''}`} />
            Refresh Odds
          </button>
          <button
            className="btn-primary"
            onClick={() => runOptimizer.mutate()}
            disabled={runOptimizer.isPending || !activeConfig}
          >
            <Play className="w-4 h-4" />
            Run Optimizer
          </button>
          <button
            className="btn-secondary"
            onClick={() => exportData.mutate()}
            disabled={exportData.isPending}
          >
            <Download className="w-4 h-4" />
            Export Excel
          </button>
        </div>
      </div>

      {/* Metric Cards */}
      {isLoading ? (
        <div className="grid grid-cols-2 lg:grid-cols-3 xl:grid-cols-6 gap-4">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="card p-5 h-24 animate-pulse bg-slate-100" />
          ))}
        </div>
      ) : (
        <div className="grid grid-cols-2 lg:grid-cols-3 xl:grid-cols-6 gap-4">
          <MetricCard
            title="Latest Odds Refresh"
            value={
              stats?.latest_odds_refresh
                ? format(new Date(stats.latest_odds_refresh), 'HH:mm')
                : 'Never'
            }
            subtitle={
              stats?.latest_odds_refresh
                ? format(new Date(stats.latest_odds_refresh), 'MMM d')
                : undefined
            }
            status={stats?.latest_odds_refresh ? 'good' : 'warning'}
            icon={<Clock className="w-4 h-4" />}
          />
          <MetricCard
            title="Matches Ready"
            value={stats?.matches_ready ?? 0}
            status="good"
            icon={<CheckCircle className="w-4 h-4" />}
          />
          <MetricCard
            title="Incomplete Matches"
            value={stats?.matches_incomplete ?? 0}
            status={(stats?.matches_incomplete ?? 0) > 0 ? 'warning' : 'good'}
            icon={<AlertTriangle className="w-4 h-4" />}
          />
          <MetricCard
            title="With Overrides"
            value={stats?.matches_with_overrides ?? 0}
            status="neutral"
            icon={<GitBranch className="w-4 h-4" />}
          />
          <MetricCard
            title="Latest Model Run"
            value={latestRun?.status ?? 'None'}
            subtitle={
              latestRun?.completed_at
                ? format(new Date(latestRun.completed_at), 'HH:mm MMM d')
                : undefined
            }
            status={
              !latestRun
                ? 'neutral'
                : latestRun.status === 'completed'
                ? 'good'
                : latestRun.status === 'failed'
                ? 'danger'
                : 'warning'
            }
            icon={<Zap className="w-4 h-4" />}
          />
          <MetricCard
            title="Avg Fit Quality"
            value={fitStatus.charAt(0).toUpperCase() + fitStatus.slice(1)}
            status={fitStatusColor as 'good' | 'warning' | 'danger' | 'neutral'}
          />
        </div>
      )}

      {/* Latest Model Run Summary */}
      {latestRun?.summary && (
        <div className="card p-5">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-semibold text-slate-700">Latest Run Summary</h3>
            <StatusBadge status={latestRun.status} />
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
            <div className="flex flex-col gap-1">
              <span className="text-xs text-slate-500">Total Matches</span>
              <span className="text-xl font-bold font-mono text-slate-800">
                {latestRun.summary.matches_total}
              </span>
            </div>
            <div className="flex flex-col gap-1">
              <span className="text-xs text-slate-500">Optimized</span>
              <span className="text-xl font-bold font-mono text-green-700">
                {latestRun.summary.optimized}
              </span>
            </div>
            <div className="flex flex-col gap-1">
              <span className="text-xs text-slate-500">Incomplete</span>
              <span
                className={`text-xl font-bold font-mono ${
                  latestRun.summary.incomplete > 0 ? 'text-amber-600' : 'text-slate-800'
                }`}
              >
                {latestRun.summary.incomplete}
              </span>
            </div>
            <div className="flex flex-col gap-1">
              <span className="text-xs text-slate-500">Warnings</span>
              <span
                className={`text-xl font-bold font-mono ${
                  latestRun.summary.warnings > 0 ? 'text-orange-600' : 'text-slate-800'
                }`}
              >
                {latestRun.summary.warnings}
              </span>
            </div>
          </div>
        </div>
      )}

      {/* Active Pool Config */}
      {activeConfig && (
        <div className="card p-5">
          <h3 className="text-sm font-semibold text-slate-700 mb-3">Active Pool Configuration</h3>
          <div className="flex flex-wrap gap-4 text-sm">
            <div>
              <span className="text-slate-500">Name: </span>
              <span className="font-medium text-slate-800">{activeConfig.name}</span>
            </div>
            <div>
              <span className="text-slate-500">Top N: </span>
              <span className="font-mono font-medium text-slate-800">{activeConfig.default_top_n}</span>
            </div>
            <div>
              <span className="text-slate-500">Ranking metric: </span>
              <span className="font-mono font-medium text-slate-800">{activeConfig.ranking_metric}</span>
            </div>
            <div>
              <span className="text-slate-500">Max goals: </span>
              <span className="font-mono font-medium text-slate-800">
                {activeConfig.candidate_max_goals}
              </span>
            </div>
          </div>
          {activeConfig.description && (
            <p className="text-xs text-slate-400 mt-2">{activeConfig.description}</p>
          )}
        </div>
      )}
    </div>
  );
}
