import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { createColumnHelper } from '@tanstack/react-table';
import { Plus, Upload, Activity } from 'lucide-react';
import { matchesApi } from '../api/matches';
import type { Match } from '../types';
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

  const importMutation = useMutation({
    mutationFn: (file: File) => matchesApi.importSchedule(file),
    onSuccess: () => {
      toast.success('Schedule imported successfully');
      qc.invalidateQueries({ queryKey: ['matches'] });
    },
    onError: (e: Error) => toast.error(`Import failed: ${e.message}`),
  });

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
            className="btn-secondary"
            onClick={() => fileRef.current?.click()}
            disabled={importMutation.isPending}
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
          <button
            className="btn-primary"
            onClick={() => toast.info('Add match form coming soon')}
          >
            <Plus className="w-4 h-4" />
            Add Match
          </button>
        </div>
      </div>

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
