import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Save, RotateCcw, Plus, Info, Copy, Trash2, CheckCircle2 } from 'lucide-react';
import { poolConfigsApi } from '../api/poolConfigs';
import { EditableScoringTable } from '../components/EditableScoringTable';
import { ConfirmDialog } from '../components/ConfirmDialog';
import { useToastContext } from '../components/Toast';
import type { ScoringMode } from '../types';

export default function ScoringRulesPage() {
  const { toast } = useToastContext();
  const qc = useQueryClient();
  const [configId, setConfigId] = useState('');
  const [resetOpen, setResetOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [savingPreset, setSavingPreset] = useState(false);
  const [presetName, setPresetName] = useState('');
  const [pendingChanges, setPendingChanges] = useState<
    Record<string, { points?: number; enabled?: boolean }>
  >({});

  const { data: configs, isLoading: configsLoading } = useQuery({
    queryKey: ['pool-configs'],
    queryFn: poolConfigsApi.list,
  });

  const activeConfig = configs?.find((c) => c.active) ?? configs?.[0];
  const effectiveConfigId = configId || activeConfig?.id || '';
  const currentConfig = configs?.find((c) => c.id === effectiveConfigId);
  const scoringMode: ScoringMode = currentConfig?.scoring_mode ?? 'standard';
  const isBinary = scoringMode === 'binary';

  const createConfig = useMutation({
    mutationFn: () =>
      poolConfigsApi.create({
        name: 'World Cup 2026',
        description: 'Default pool configuration',
      }),
    onSuccess: (created) => {
      toast.success('Pool configuration created with default scoring rules');
      setConfigId(created.id);
      qc.invalidateQueries({ queryKey: ['pool-configs'] });
    },
    onError: (e: Error) => toast.error(`Could not create configuration: ${e.message}`),
  });

  const hasConfigs = (configs?.length ?? 0) > 0;

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

  const updateConfig = useMutation({
    mutationFn: (payload: Parameters<typeof poolConfigsApi.update>[1]) =>
      poolConfigsApi.update(effectiveConfigId, payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['pool-configs'] }),
    onError: (e: Error) => toast.error(`Update failed: ${e.message}`),
  });

  const duplicateConfig = useMutation({
    mutationFn: (name: string) => poolConfigsApi.duplicate(effectiveConfigId, { name }),
    onSuccess: (created) => {
      toast.success(`Saved as new preset "${created.name}"`);
      setSavingPreset(false);
      setPresetName('');
      setConfigId(created.id);
      setPendingChanges({});
      qc.invalidateQueries({ queryKey: ['pool-configs'] });
    },
    onError: (e: Error) => toast.error(`Could not save preset: ${e.message}`),
  });

  const setActive = useMutation({
    mutationFn: () => poolConfigsApi.setActive(effectiveConfigId),
    onSuccess: () => {
      toast.success('Preset set as active');
      qc.invalidateQueries({ queryKey: ['pool-configs'] });
    },
    onError: (e: Error) => toast.error(`Could not activate: ${e.message}`),
  });

  const deleteConfig = useMutation({
    mutationFn: () => poolConfigsApi.delete(effectiveConfigId),
    onSuccess: () => {
      toast.success('Preset deleted');
      setConfigId('');
      setPendingChanges({});
      qc.invalidateQueries({ queryKey: ['pool-configs'] });
    },
    onError: (e: Error) => toast.error(`Could not delete: ${e.message}`),
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

  const handleSavePreset = () => {
    const name = presetName.trim();
    if (!name) {
      toast.error('Enter a name for the preset');
      return;
    }
    duplicateConfig.mutate(name);
  };

  const hasPending = Object.keys(pendingChanges).length > 0;

  return (
    <div className="flex flex-col gap-5">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold text-slate-800">Scoring Rules</h2>
          <p className="text-sm text-slate-500 mt-0.5">Configure points for each prediction outcome</p>
        </div>
        {hasConfigs && !isBinary && (
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
        )}
      </div>

      {/* How it works */}
      <div className="card p-4 flex items-start gap-2 border-l-4 border-l-red-700">
        <Info className="w-5 h-5 text-red-700 shrink-0 mt-0.5" />
        <div className="text-xs text-slate-600 leading-relaxed">
          <p>
            Scoring rules define how many points each prediction outcome is worth. The
            optimizer uses these points to recommend the score that maximises your
            expected points per match.
          </p>
          <p className="mt-1">
            Each <strong>preset</strong> is a saved scoring system. Edit the one you have,
            or use <strong>Save as new preset</strong> to keep the current rules as a
            separate copy instead of overwriting them. The <strong>active</strong> preset
            is the one the optimizer uses.
          </p>
        </div>
      </div>

      {/* Empty state — no pool configuration yet */}
      {!configsLoading && !hasConfigs ? (
        <div className="card p-8 flex flex-col items-center text-center gap-3">
          <p className="text-sm font-medium text-slate-700">No pool configuration yet</p>
          <p className="text-xs text-slate-500 max-w-md">
            A pool configuration holds your scoring rules and optimizer settings. Create one
            to get started — it comes pre-loaded with the standard World Cup scoring rules,
            which you can then customise.
          </p>
          <button
            className="btn-primary mt-1"
            onClick={() => createConfig.mutate()}
            disabled={createConfig.isPending}
          >
            <Plus className="w-4 h-4" />
            {createConfig.isPending ? 'Creating…' : 'Create default configuration'}
          </button>
        </div>
      ) : (
        <>
          {/* Preset (config) management */}
          <div className="card p-4 flex flex-col gap-3">
            <div className="flex flex-wrap items-center gap-3">
              <label className="text-xs font-medium text-slate-600">Preset</label>
              <select
                className="input w-56 text-sm"
                value={effectiveConfigId}
                onChange={(e) => {
                  setConfigId(e.target.value);
                  setPendingChanges({});
                  setSavingPreset(false);
                }}
              >
                {configs?.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name} {c.active ? '(active)' : ''}
                  </option>
                ))}
              </select>

              {currentConfig && !currentConfig.active && (
                <button
                  className="btn-secondary"
                  onClick={() => setActive.mutate()}
                  disabled={setActive.isPending}
                  title="Make this the preset the optimizer uses"
                >
                  <CheckCircle2 className="w-4 h-4" />
                  Set Active
                </button>
              )}

              <button
                className="btn-secondary"
                onClick={() => setSavingPreset((v) => !v)}
                title="Save the current rules as a new preset"
              >
                <Copy className="w-4 h-4" />
                Save as new preset
              </button>

              {(configs?.length ?? 0) > 1 && (
                <button
                  className="btn-secondary text-red-700"
                  onClick={() => setDeleteOpen(true)}
                  disabled={deleteConfig.isPending}
                  title="Delete this preset"
                >
                  <Trash2 className="w-4 h-4" />
                  Delete
                </button>
              )}
            </div>

            {savingPreset && (
              <div className="flex flex-wrap items-center gap-2 border-t border-slate-100 pt-3">
                <input
                  className="input text-sm w-64"
                  placeholder="New preset name"
                  value={presetName}
                  autoFocus
                  onChange={(e) => setPresetName(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && handleSavePreset()}
                />
                <button
                  className="btn-primary"
                  onClick={handleSavePreset}
                  disabled={duplicateConfig.isPending}
                >
                  <Save className="w-4 h-4" />
                  {duplicateConfig.isPending ? 'Saving…' : 'Save copy'}
                </button>
                <button
                  className="btn-secondary"
                  onClick={() => {
                    setSavingPreset(false);
                    setPresetName('');
                  }}
                >
                  Cancel
                </button>
                <span className="text-xs text-slate-400">
                  Copies the current rules &amp; settings into a new preset.
                </span>
              </div>
            )}
          </div>

          {/* Scoring mode selector */}
          <div className="card p-4 flex flex-col gap-3">
            <div className="flex flex-wrap items-center gap-3">
              <label className="text-xs font-medium text-slate-600">Scoring Mode</label>
              <div className="inline-flex rounded-lg border border-slate-200 overflow-hidden">
                <button
                  className={`px-3 py-1.5 text-sm ${
                    !isBinary ? 'bg-red-700 text-white' : 'bg-white text-slate-600 hover:bg-slate-50'
                  }`}
                  onClick={() => !isBinary || updateConfig.mutate({ scoring_mode: 'standard' })}
                  disabled={updateConfig.isPending}
                >
                  Standard
                </button>
                <button
                  className={`px-3 py-1.5 text-sm border-l border-slate-200 ${
                    isBinary ? 'bg-red-700 text-white' : 'bg-white text-slate-600 hover:bg-slate-50'
                  }`}
                  onClick={() => isBinary || updateConfig.mutate({ scoring_mode: 'binary' })}
                  disabled={updateConfig.isPending}
                >
                  Binary
                </button>
              </div>
            </div>
            <p className="text-xs text-slate-500">
              {isBinary ? (
                <>
                  <strong>Binary:</strong> a prediction earns the result points for a correct
                  outcome (home win, draw or away win) plus the total-goals points for the
                  correct total goals scored (home + away). The two are awarded independently
                  (0, 1 or 2 categories), and the rule table below is ignored.
                </>
              ) : (
                <>
                  <strong>Standard:</strong> the highest-value applicable rule from the table
                  below is awarded for each match.
                </>
              )}
            </p>
          </div>

          {/* Binary point configuration */}
          {isBinary && currentConfig && (
            <div className="card p-4 flex flex-col gap-3">
              <h3 className="text-sm font-semibold text-slate-700">Binary Points</h3>
              <div className="flex flex-wrap items-center gap-6">
                <label className="flex items-center gap-2 text-sm text-slate-600">
                  Correct result
                  <input
                    key={`result-${currentConfig.id}`}
                    type="number"
                    step="0.5"
                    className="w-20 text-right input font-mono text-sm"
                    defaultValue={currentConfig.binary_result_points}
                    onBlur={(e) => {
                      const v = parseFloat(e.target.value);
                      if (!isNaN(v) && v !== currentConfig.binary_result_points) {
                        updateConfig.mutate({ binary_result_points: v });
                      }
                    }}
                  />
                </label>
                <label className="flex items-center gap-2 text-sm text-slate-600">
                  Correct total goals
                  <input
                    key={`total-${currentConfig.id}`}
                    type="number"
                    step="0.5"
                    className="w-20 text-right input font-mono text-sm"
                    defaultValue={currentConfig.binary_total_goals_points}
                    onBlur={(e) => {
                      const v = parseFloat(e.target.value);
                      if (!isNaN(v) && v !== currentConfig.binary_total_goals_points) {
                        updateConfig.mutate({ binary_total_goals_points: v });
                      }
                    }}
                  />
                </label>
              </div>
            </div>
          )}

          {/* Standard mode: editable rule table */}
          {!isBinary &&
            (isLoading ? (
              <div className="card p-8 text-center text-slate-400">Loading rules...</div>
            ) : rules ? (
              <EditableScoringTable
                rules={rules}
                onChange={handleChange}
                loading={updateRule.isPending}
              />
            ) : (
              <div className="card p-8 text-center text-slate-400">Select a preset</div>
            ))}
        </>
      )}

      <ConfirmDialog
        open={resetOpen}
        title="Reset Scoring Rules"
        message="This will reset all scoring rules to their defaults for this preset. Any custom changes will be lost."
        confirmLabel="Reset"
        variant="warning"
        onConfirm={() => {
          setResetOpen(false);
          resetRules.mutate();
        }}
        onCancel={() => setResetOpen(false)}
      />

      <ConfirmDialog
        open={deleteOpen}
        title="Delete Preset"
        message={`This will permanently delete the preset "${currentConfig?.name ?? ''}" and its scoring rules. This cannot be undone.`}
        confirmLabel="Delete"
        variant="warning"
        onConfirm={() => {
          setDeleteOpen(false);
          deleteConfig.mutate();
        }}
        onCancel={() => setDeleteOpen(false)}
      />
    </div>
  );
}
