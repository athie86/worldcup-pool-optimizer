import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { createColumnHelper } from '@tanstack/react-table';
import { FileText, FileSpreadsheet, Download } from 'lucide-react';
import { exportsApi } from '../api/exports';
import { modelRunsApi } from '../api/modelRuns';
import type { ExportRecord } from '../types';
import { DataTable } from '../components/DataTable';
import { ExportButton } from '../components/ExportButton';
import { useToastContext } from '../components/Toast';
import { format } from 'date-fns';

const colHelper = createColumnHelper<ExportRecord>();

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export default function ExportsPage() {
  const { toast } = useToastContext();
  const qc = useQueryClient();

  const { data: exports, isLoading } = useQuery({
    queryKey: ['exports'],
    queryFn: exportsApi.list,
  });

  const { data: runs } = useQuery({
    queryKey: ['model-runs'],
    queryFn: modelRunsApi.list,
  });

  const createExport = useMutation({
    mutationFn: (fmt: 'csv' | 'xlsx') => {
      const runId = runs?.[0]?.id;
      if (!runId) throw new Error('No model run available. Run the optimizer first.');
      return exportsApi.create({ format: fmt, model_run_id: runId });
    },
    onSuccess: (record) => {
      toast.success('Export created successfully');
      qc.invalidateQueries({ queryKey: ['exports'] });
      window.open(exportsApi.download(record.id), '_blank');
    },
    onError: (e: Error) => toast.error(`Export failed: ${e.message}`),
  });

  const columns = [
    colHelper.accessor('format', {
      header: 'Format',
      cell: (i) => (
        <div className="flex items-center gap-2">
          {i.getValue() === 'xlsx' ? (
            <FileSpreadsheet className="w-4 h-4 text-green-600" />
          ) : (
            <FileText className="w-4 h-4 text-blue-600" />
          )}
          <span className="uppercase text-xs font-mono font-semibold text-slate-700">
            {i.getValue()}
          </span>
        </div>
      ),
    }),
    colHelper.accessor('filename', {
      header: 'Filename',
      cell: (i) => (
        <span className="font-mono text-sm text-slate-700">{i.getValue()}</span>
      ),
    }),
    colHelper.accessor('created_at', {
      header: 'Created',
      cell: (i) => (
        <span className="font-mono text-xs text-slate-600">
          {format(new Date(i.getValue()), 'MMM d, yyyy HH:mm')}
        </span>
      ),
    }),
    colHelper.accessor('size_bytes', {
      header: 'Size',
      cell: (i) => {
        const v = i.getValue();
        return (
          <span className="font-mono text-xs text-slate-500">
            {v !== undefined ? formatBytes(v) : '—'}
          </span>
        );
      },
    }),
    colHelper.accessor('model_run_id', {
      header: 'Model Run',
      cell: (i) => {
        const rid = i.getValue();
        if (!rid) return <span className="text-slate-300">—</span>;
        const run = runs?.find((r) => r.id === rid);
        return (
          <span className="font-mono text-xs text-slate-500">
            {run ? format(new Date(run.started_at), 'MMM d HH:mm') : rid.slice(0, 8)}
          </span>
        );
      },
    }),
    colHelper.display({
      id: 'download',
      header: '',
      cell: ({ row }) => (
        <a
          href={exportsApi.download(row.original.id)}
          target="_blank"
          rel="noopener noreferrer"
          className="flex items-center gap-1 text-xs text-blue-600 hover:text-blue-800 px-2 py-1 rounded hover:bg-blue-50"
        >
          <Download className="w-3.5 h-3.5" />
          Download
        </a>
      ),
    }),
  ];

  return (
    <div className="flex flex-col gap-5">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold text-slate-800">Exports</h2>
          <p className="text-sm text-slate-500 mt-0.5">
            {exports ? `${exports.length} export${exports.length !== 1 ? 's' : ''}` : 'Loading...'}
          </p>
        </div>
        <ExportButton onExport={(fmt) => createExport.mutate(fmt)} loading={createExport.isPending} />
      </div>

      <div className="card overflow-hidden">
        {isLoading ? (
          <div className="p-8 text-center text-slate-400">Loading exports...</div>
        ) : exports && exports.length > 0 ? (
          <DataTable data={exports} columns={columns} pageSize={20} />
        ) : (
          <div className="p-10 flex flex-col items-center gap-3 text-center">
            <FileSpreadsheet className="w-10 h-10 text-slate-200" />
            <p className="text-slate-400 text-sm">No exports yet. Create one using the button above.</p>
          </div>
        )}
      </div>
    </div>
  );
}
