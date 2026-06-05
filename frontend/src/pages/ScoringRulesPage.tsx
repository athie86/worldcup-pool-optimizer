import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Save, RotateCcw } from 'lucide-react';
import { poolConfigsApi } from '../api/poolConfigs';
import { EditableScoringTable } from '../components/EditableScoringTable';
import { ConfirmDialog } from '../components/ConfirmDialog';
import { useToastContext } from '../components/Toast';

export default function ScoringRulesPage() {
  const { toast } = useToastContext();
  const qc = useQueryClient();
  const [configId, setConfigId] = useState('');
  const [resetOpen, setResetOpen] = useState(false);
  const [pendingChanges, setPendingChanges] = useState<
    Record<string, { points?: number; enabled?: boolean }>
  >({});

  const { data: configs } = useQuery({
    queryKey: ['pool-configs'],
    queryFn: poolConfigsApi.list,
  });

  const activeConfig = configs?.find((c) => c.active) ?? configs?.[0];
  const effectiveConfigId = configId || activeConfig?.id || '';

  const { data: rules, isLoading } = useQuery({
    queryKey: ['scoring-rules', effectiveConfigId],
    queryFn: () => poolConfigsApi.getScoringRules(effectiveConfigId),
    enabled: !!effectiveConfigId,
  });

  const updateRule = useMutation({
    mutationFn: ({
      ruleId,
      payload,
    }: {
      ruleId: string;
      payload: { points?: number; enabled?: boolean };
    }) => poolConfigsApi.updateScoringRule(effectiveConfigId, ruleId, payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['scoring-rules', effectiveConfigId] });
    },
    onError: (e: Error) => toast.error(`Update failed: ${e.message}`),
  });

  const resetRules = useMutation({
    mutationFn: () => poolConfigsApi.resetScoringRules(effectiveConfigId),
    onSuccess: () => {
      toast.success('Scoring rules reset to defaults');
      setPendingChanges({});
      qc.invalidateQueries({ queryKey: ['scoring-rules', effectiveConfigId] });
    },
    onError: (e: Error) => toast.error(`Reset failed: ${e.message}`),
  });

  const handleSaveAll = async () => {
    const entries = Object.entries(pendingChanges);
    if (entries.length === 0) {
      toast.info('No changes to save');
      return;
    }
    let errors = 0;
    for (const [ruleId, payload] of entries) {
      try {
        await updateRule.mutateAsync({ ruleId, payload });
      } catch {
        errors++;
      }
    }
    if (errors === 0) {
      toast.success(`Saved ${entries.length} rule changes`);
      setPendingChanges({});
    } else {
      toast.error(`${errors} changes failed to save`);
    }
  };

  const handleChange = (ruleId: string, changes: { points?: number; enabled?: boolean }) => {
    // Immediate save for toggles
    if (changes.enabled !== undefined) {
      updateRule.mutate({ ruleId, payload: { enabled: changes.enabled } });
    } else {
      setPendingChanges((prev) => ({
        ...prev,
        [ruleId]: { ...prev[ruleId], ...changes },
      }));
    }
  };

  const hasPending = Object.keys(pendingChanges).length > 0;

  return (
    <div className="flex flex-col gap-5">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold text-slate-800">Scoring Rules</h2>
          <p className="text-sm text-slate-500 mt-0.5">Configure points for each prediction outcome</p>
        </div>
        <div className="flex items-center gap-2">
          <button
            className="btn-secondary"
            onClick={() => setResetOpen(true)}
            disabled={resetRules.isPending}
          >
            <RotateCcw className="w-4 h-4" />
            Reset to Defaults
          </button>
          <button
            className="btn-primary"
            onClick={handleSaveAll}
            disabled={!hasPending || updateRule.isPending}
          >
            <Save className="w-4 h-4" />
            Save Changes {hasPending ? `(${Object.keys(pendingChanges).length})` : ''}
          </button>
        </div>
      </div>

      {/* Config selector */}
      <div className="card p-4 flex items-center gap-4">
        <label className="text-xs font-medium text-slate-600">Pool Configuration</label>
        <select
          className="input w-56 text-sm"
          value={effectiveConfigId}
          onChange={(e) => setConfigId(e.target.value)}
        >
          {configs?.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name} {c.active ? '(active)' : ''}
            </option>
          ))}
        </select>
      </div>

      {isLoading ? (
        <div className="card p-8 text-center text-slate-400">Loading rules...</div>
      ) : rules ? (
        <EditableScoringTable
          rules={rules}
          onChange={handleChange}
          loading={updateRule.isPending}
        />
      ) : (
        <div className="card p-8 text-center text-slate-400">Select a pool configuration</div>
      )}

      <ConfirmDialog
        open={resetOpen}
        title="Reset Scoring Rules"
        message="This will reset all scoring rules to their defaults for this configuration. Any custom changes will be lost."
        confirmLabel="Reset"
        variant="warning"
        onConfirm={() => {
          setResetOpen(false);
          resetRules.mutate();
        }}
        onCancel={() => setResetOpen(false)}
      />
    </div>
  );
}
