import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { createColumnHelper } from '@tanstack/react-table';
import { Upload, Activity, Database, FileDown, Info, X } from 'lucide-react';
import { matchesApi } from '../api/matches';
import type { Match, ImportSummary } from '../types';
import { DataTable } from '../components/DataTable';
import { StatusBadge } from '../components/StatusBadge';
import { FitQualityBadge } from '../components/FitQualityBadge';
import { OverrideBadge } from '../components/OverrideBadge';
import { useToastContext } from '../components/Toast';
import { format } from 'date-fns';
import { useNavigate } from 'react-router-dom';

const columnHelper = createColumnHelper<Match>();

const STAGES = ['', 'group', 'round_of_32', 'round_of_16', 'quarter_final', 'semi_final', 'final'];
const STATUSES = ['', 'scheduled', 'live', 'complete', 'incomplete'];

export default function MatchesPage() {
  const { toast } = useToastContext();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [stageFilter, setStageFilter] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [page, setPage] = useState(1);
  const [importOpen, setImportOpen] = useState(false);
  const [importResult, setImportResult] = useState<ImportSummary | null>(null);
  const fileRef = React.useRef<HTMLInputElement>(null);

  const { data, isLoading } = useQuery({
    queryKey: ['matches', { stage: stageFilter, status: statusFilter, page }],
    queryFn: () =>
      matchesApi.list({
        stage: stageFilter || undefined,
        status: statusFilter || undefined,
        page,
        page_size: 50,
      }),
  });

  const handleImportSuccess = (summary: ImportSummary) => {
    setImportResult(summary);
    if (summary.errors.length > 0) {
      toast.info(`${summary.message} (${summary.errors.length} row(s) skipped)`);
    } else {
      toast.success(summary.message);
    }
    qc.invalidateQueries({ queryKey: ['matches'] });
    qc.invalidateQueries({ queryKey: ['dashboard'] });
  };

  const importMutation = useMutation({
    mutationFn: (file: File) => matchesApi.importSchedule(file),
    onSuccess: handleImportSuccess,
    onError: (e: Error) => toast.error(`Import failed: ${e.message}`),
  });

  const providerImportMutation = useMutation({
    mutationFn: () => matchesApi.importProviderSchedule(),
    onSuccess: handleImportSuccess,
    onError: (e: Error) => toast.error(`Import failed: ${e.message}`),
  });

  const downloadTemplate = () => {
    const header =
      'match_number,stage,group_label,home_team,away_team,kickoff_at,venue,city,country,scoring_basis,is_complete_for_optimization';
    const sample =
      '1,group,A,Spain,Japan,2026-06-11T15:00:00Z,SoFi Stadium,Inglewood,USA,ninety_minutes,true';
    const blob = new Blob([`${header}\n${sample}\n`], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'match-schedule-template.csv';
    a.click();
    URL.revokeObjectURL(url);
  };

  const importBusy = importMutation.isPending || providerImportMutation.isPending;

  const columns = [
    columnHelper.accessor('match_number', {
      header: '#',
      cell: (i) => <span className="font-mono text-slate-500">{i.getValue() ?? '—'}</span>,
    }),
    columnHelper.accessor('stage', {
      header: 'Stage',
      cell: (i) => (
        <span className="text-xs text-slate-600 capitalize">
          {i.getValue().replace(/_/g, ' ')}
        </span>
      ),
    }),
    columnHelper.accessor('group_label', {
      header: 'Group',
      cell: (i) => <span className="text-xs text-slate-500">{i.getValue() ?? '—'}</span>,
    }),
    columnHelper.accessor('kickoff_at', {
      header: 'Date / Time',
      cell: (i) => {
        const v = i.getValue();
        if (!v) return <span className="text-slate-400">TBD</span>;
        return (
          <span className="font-mono text-xs text-slate-600">
            {format(new Date(v), 'MMM d, HH:mm')}
          </span>
        );
      },
    }),
    columnHelper.display({
      id: 'home_team',
      header: 'Home',
      cell: ({ row }) => (
        <span className="font-medium text-slate-700">
          {row.original.home_team ?? row.original.home_placeholder ?? '?'}
        </span>
      ),
    }),
    columnHelper.display({
      id: 'away_team',
      header: 'Away',
      cell: ({ row }) => (
        <span className="font-medium text-slate-700">
          {row.original.away_team ?? row.original.away_placeholder ?? '?'}
        </span>
      ),
    }),
    columnHelper.accessor('venue', {
      header: 'Venue',
      cell: (i) => <span className="text-xs text-slate-500">{i.getValue() ?? '—'}</span>,
    }),
    columnHelper.accessor('scoring_basis', {
      header: 'Basis',
      cell: (i) => (
        <span className="text-xs font-mono text-slate-500">{i.getValue()}</span>
      ),
    }),
    columnHelper.accessor('status', {
      header: 'Status',
      cell: (i) => <StatusBadge status={i.getValue()} />,
    }),
    columnHelper.accessor('fit_status', {
      header: 'Fit',
      cell: (i) => {
        const v = i.getValue();
        return v ? <FitQualityBadge status={v} /> : <span className="text-slate-300 text-xs">—</span>;
      },
    }),
    columnHelper.display({
      id: 'override',
      header: 'Override',
      cell: ({ row }) => <OverrideBadge hasOverrides={row.original.has_overrides ?? false} />,
    }),
    columnHelper.display({
      id: 'actions',
      header: '',
      cell: ({ row }) => (
        <div className="flex items-center gap-1.5">
          <button
            className="text-xs text-blue-600 hover:text-blue-800 px-2 py-1 rounded hover:bg-blue-50"
            onClick={() => navigate(`/odds-overrides?match=${row.original.id}`)}
          >
            Odds
          </button>
          <button
            className="text-xs text-slate-600 hover:text-slate-800 px-2 py-1 rounded hover:bg-slate-100 flex items-center gap-1"
            onClick={() => navigate(`/diagnostics?match=${row.original.id}`)}
          >
            <Activity className="w-3 h-3" />
            Diag
          </button>
        </div>
      ),
    }),
  ];

  const matches = data?.items ?? [];

  return (
    <div className="flex flex-col gap-5">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold text-slate-800">Matches</h2>
          <p className="text-sm text-slate-500 mt-0.5">
            {data ? `${data.total} matches total` : 'Loading...'}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            className="btn-primary"
            onClick={() => setImportOpen((v) => !v)}
          >
            <Upload className="w-4 h-4" />
            Import Schedule
          </button>
          <input
            ref={fileRef}
            type="file"
            accept=".csv,.json"
            className="hidden"
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) importMutation.mutate(file);
              e.target.value = '';
            }}
          />
        </div>
      </div>

      {/* Import schedule panel with instructions */}
      {importOpen && (
        <div className="card p-5 flex flex-col gap-4 border-l-4 border-l-red-700">
          <div className="flex items-start justify-between">
            <div className="flex items-start gap-2">
              <Info className="w-5 h-5 text-red-700 shrink-0 mt-0.5" />
              <div>
                <h3 className="text-sm font-semibold text-slate-800">Import the match schedule</h3>
                <p className="text-xs text-slate-500 mt-0.5">
                  Choose one of the two methods below. You can re-import at any time —
                  existing matches (matched by match number or provider event ID) are
                  updated rather than duplicated.
                </p>
              </div>
            </div>
            <button
              className="text-slate-400 hover:text-slate-600"
              onClick={() => setImportOpen(false)}
              aria-label="Close"
            >
              <X className="w-4 h-4" />
            </button>
          </div>

          <div className="grid gap-4 md:grid-cols-2">
            {/* Method 1: provider */}
            <div className="rounded-xl border border-slate-200 p-4 flex flex-col gap-2">
              <div className="flex items-center gap-2 text-sm font-semibold text-slate-700">
                <Database className="w-4 h-4 text-red-700" />
                Option A — From The Odds API
              </div>
              <p className="text-xs text-slate-500">
                Pulls the official fixtures directly from your configured odds provider.
                This also links each match to its odds event, so <strong>Refresh Odds</strong>{' '}
                works automatically afterwards. Requires <code className="font-mono">ODDS_API_KEY</code>{' '}
                to be set.
              </p>
              <button
                className="btn-primary self-start mt-1"
                onClick={() => providerImportMutation.mutate()}
                disabled={importBusy}
              >
                <Database className="w-4 h-4" />
                {providerImportMutation.isPending ? 'Importing…' : 'Import from provider'}
              </button>
            </div>

            {/* Method 2: file */}
            <div className="rounded-xl border border-slate-200 p-4 flex flex-col gap-2">
              <div className="flex items-center gap-2 text-sm font-semibold text-slate-700">
                <Upload className="w-4 h-4 text-red-700" />
                Option B — Upload a CSV or JSON file
              </div>
              <p className="text-xs text-slate-500">
                Upload your own schedule. The CSV needs a header row with columns:
                <code className="font-mono block mt-1 text-[11px] text-slate-600">
                  match_number, stage, group_label, home_team, away_team, kickoff_at,
                  venue, city, country, scoring_basis, is_complete_for_optimization
                </code>
                Only <strong>stage</strong>, <strong>home_team</strong> and{' '}
                <strong>away_team</strong> are required. Teams are created automatically.
              </p>
              <div className="flex items-center gap-2 mt-1">
                <button
                  className="btn-primary"
                  onClick={() => fileRef.current?.click()}
                  disabled={importBusy}
                >
                  <Upload className="w-4 h-4" />
                  {importMutation.isPending ? 'Importing…' : 'Choose file'}
                </button>
                <button className="btn-secondary" onClick={downloadTemplate}>
                  <FileDown className="w-4 h-4" />
                  Download template
                </button>
              </div>
            </div>
          </div>

          {importResult && (
            <div className="rounded-xl bg-slate-50 border border-slate-200 p-3 text-xs text-slate-600">
              <p className="font-medium text-slate-700">{importResult.message}</p>
              <p className="mt-1">
                Created {importResult.created} · Updated {importResult.updated} · New teams{' '}
                {importResult.teams_created}
                {importResult.skipped > 0 ? ` · Skipped ${importResult.skipped}` : ''}
              </p>
              {importResult.errors.length > 0 && (
                <ul className="mt-2 list-disc list-inside text-amber-700">
                  {importResult.errors.slice(0, 5).map((err, i) => (
                    <li key={i}>{err}</li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </div>
      )}

      {/* Filters */}
      <div className="card p-4 flex flex-wrap items-center gap-4">
        <div className="flex items-center gap-2">
          <label className="text-xs font-medium text-slate-600">Stage</label>
          <select
            className="input w-40 text-sm"
            value={stageFilter}
            onChange={(e) => { setStageFilter(e.target.value); setPage(1); }}
          >
            {STAGES.map((s) => (
              <option key={s} value={s}>
                {s ? s.replace(/_/g, ' ') : 'All stages'}
              </option>
            ))}
          </select>
        </div>
        <div className="flex items-center gap-2">
          <label className="text-xs font-medium text-slate-600">Status</label>
          <select
            className="input w-40 text-sm"
            value={statusFilter}
            onChange={(e) => { setStatusFilter(e.target.value); setPage(1); }}
          >
            {STATUSES.map((s) => (
              <option key={s} value={s}>
                {s ? s.charAt(0).toUpperCase() + s.slice(1) : 'All statuses'}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Table */}
      <div className="card overflow-hidden">
        {isLoading ? (
          <div className="p-8 text-center text-slate-400">Loading matches...</div>
        ) : (
          <DataTable data={matches} columns={columns} pageSize={50} />
        )}
      </div>
    </div>
  );
}
