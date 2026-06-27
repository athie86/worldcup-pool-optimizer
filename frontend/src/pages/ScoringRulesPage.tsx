import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Save,
  RotateCcw,
  Plus,
  Info,
  Copy,
  Trash2,
  CheckCircle2,
  ListChecks,
  Layers,
} from 'lucide-react';
import { poolConfigsApi } from '../api/poolConfigs';
import { EditableScoringTable } from '../components/EditableScoringTable';
import { ConfirmDialog } from '../components/ConfirmDialog';
import { useToastContext } from '../components/Toast';
import type { ScoringMode, PoolConfig } from '../types';

/** Small read-only badge that makes a ruleset's scoring type unmistakable. */
function ModeBadge({ mode }: { mode: ScoringMode }) {
  const binary = mode === 'binary';
  return (
    <span
      className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-semibold ${
        binary ? 'bg-violet-100 text-violet-700' : 'bg-sky-100 text-sky-700'
      }`}
    >
      {binary ? <Layers className="w-3 h-3" /> : <ListChecks className="w-3 h-3" />}
      {binary ? 'Binary' : 'Standard'}
    </span>
  );
}

export default function ScoringRulesPage() {
  const { toast } = useToastContext();
  const qc = useQueryClient();

  // The page starts blank: no ruleset is selected until the user picks one.
  const [selectedId, setSelectedId] = useState('');
  const [resetOpen, setResetOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);

  // "New ruleset from scratch" form state.
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState('');
  const [newMode, setNewMode] = useState<ScoringMode>('standard');

  // "Save as copy" form state.
  const [duplicating, setDuplicating] = useState(false);
  const [copyName, setCopyName] = useState('');

  const [pendingChanges, setPendingChanges] = useState<
    Record<string, { points?: number; enabled?: boolean }>
  >({});

  const { data: configs, isLoading: configsLoading } = useQuery({
    queryKey: ['pool-configs'],
    queryFn: poolConfigsApi.list,
  });

  const currentConfig: PoolConfig | undefined = configs?.find((c) => c.id === selectedId);
  const scoringMode: ScoringMode = currentConfig?.scoring_mode ?? 'standard';
  const isBinary = scoringMode === 'binary';
  const hasSelection = !!currentConfig;

  const resetTransient = () => {
    setPendingChanges({});
    setDuplicating(false);
    setCopyName('');
  };

  const selectConfig = (id: string) => {
    setSelectedId(id);
    resetTransient();
  };

  const { data: rules, isLoading: rulesLoading } = useQuery({
    queryKey: ['scoring-rules', selectedId],
    queryFn: () => poolConfigsApi.getScoringRules(selectedId),
    // Only fetch rules for a selected, standard-mode ruleset. Binary rulesets
    // ignore the rule table entirely, so there is nothing to load.
    enabled: hasSelection && !isBinary,
  });

  const createConfig = useMutation({
    mutationFn: (payload: { name: string; scoring_mode: ScoringMode }) =>
      poolConfigsApi.create({
        name: payload.name,
        description: 'Created from Scoring Rules',
        scoring_mode: payload.scoring_mode,
        // The first-ever ruleset becomes active so the optimizer always has a
        // default. Additional rulesets must never silently steal "active" from
        // the one the optimizer currently uses — the user activates them explicitly.
        active: (configs?.length ?? 0) === 0,
      }),
    onSuccess: (created) => {
      toast.success(`Ruleset "${created.name}" created`);
      setCreating(false);
      setNewName('');
      setNewMode('standard');
      selectConfig(created.id);
      qc.invalidateQueries({ queryKey: ['pool-configs'] });
    },
    onError: (e: Error) => toast.error(`Could not create ruleset: ${e.message}`),
  });

  const updateRule = useMutation({
    mutationFn: ({
      ruleId,
      payload,
    }: {
      ruleId: string;
      payload: { points?: number; enabled?: boolean };
    }) => poolConfigsApi.updateScoringRule(selectedId, ruleId, payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['scoring-rules', selectedId] });
    },
    onError: (e: Error) => toast.error(`Update failed: ${e.message}`),
  });

  const updateConfig = useMutation({
    mutationFn: (payload: Parameters<typeof poolConfigsApi.update>[1]) =>
      poolConfigsApi.update(selectedId, payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['pool-configs'] }),
    onError: (e: Error) => toast.error(`Update failed: ${e.message}`),
  });

  const duplicateConfig = useMutation({
    mutationFn: (name: string) => poolConfigsApi.duplicate(selectedId, { name }),
    onSuccess: (created) => {
      toast.success(`Saved as new ruleset "${created.name}"`);
      selectConfig(created.id);
      qc.invalidateQueries({ queryKey: ['pool-configs'] });
    },
    onError: (e: Error) => toast.error(`Could not save copy: ${e.message}`),
  });

  const setActive = useMutation({
    mutationFn: () => poolConfigsApi.setActive(selectedId),
    onSuccess: () => {
      toast.success('Ruleset set as active — the optimizer will use it by default');
      qc.invalidateQueries({ queryKey: ['pool-configs'] });
    },
    onError: (e: Error) => toast.error(`Could not activate: ${e.message}`),
  });

  const deleteConfig = useMutation({
    mutationFn: () => poolConfigsApi.delete(selectedId),
    onSuccess: () => {
      toast.success('Ruleset deleted');
      setSelectedId('');
      resetTransient();
      qc.invalidateQueries({ queryKey: ['pool-configs'] });
    },
    onError: (e: Error) => toast.error(`Could not delete: ${e.message}`),
  });

  const resetRules = useMutation({
    mutationFn: () => poolConfigsApi.resetScoringRules(selectedId),
    onSuccess: () => {
      toast.success('Scoring rules reset to defaults');
      setPendingChanges({});
      qc.invalidateQueries({ queryKey: ['scoring-rules', selectedId] });
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
      toast.success(`Saved ${entries.length} rule change${entries.length > 1 ? 's' : ''}`);
      setPendingChanges({});
    } else {
      toast.error(`${errors} change(s) failed to save`);
    }
  };

  const handleChange = (ruleId: string, changes: { points?: number; enabled?: boolean }) => {
    // Toggles save immediately; point edits batch into "Save Changes".
    if (changes.enabled !== undefined) {
      updateRule.mutate({ ruleId, payload: { enabled: changes.enabled } });
    } else {
      setPendingChanges((prev) => ({
        ...prev,
        [ruleId]: { ...prev[ruleId], ...changes },
      }));
    }
  };

  const handleCreate = () => {
    const name = newName.trim();
    if (!name) {
      toast.error('Enter a name for the new ruleset');
      return;
    }
    createConfig.mutate({ name, scoring_mode: newMode });
  };

  const handleSaveCopy = () => {
    const name = copyName.trim();
    if (!name) {
      toast.error('Enter a name for the copy');
      return;
    }
    duplicateConfig.mutate(name);
  };

  const hasPending = Object.keys(pendingChanges).length > 0;
  const noConfigs = !configsLoading && (configs?.length ?? 0) === 0;

  return (
    <div className="flex flex-col gap-5">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold text-slate-800">Scoring Rules</h2>
          <p className="text-sm text-slate-500 mt-0.5">
            Each ruleset is a self-contained scoring system the optimizer can run
          </p>
        </div>
      </div>

      {/* How it works */}
      <div className="card p-4 flex items-start gap-2 border-l-4 border-l-red-700">
        <Info className="w-5 h-5 text-red-700 shrink-0 mt-0.5" />
        <div className="text-xs text-slate-600 leading-relaxed">
          <p>
            A <strong>ruleset</strong> bundles a scoring <strong>type</strong> (Standard
            or Binary) with its point values. The optimizer always runs exactly one
            ruleset — the one you pick on the Optimizer page (the{' '}
            <strong>active</strong> ruleset is selected there by default).
          </p>
          <p className="mt-1">
            A ruleset's type is fixed when you create it, so Standard and Binary scoring
            can never get mixed up. To use a different type, create a new ruleset.
          </p>
        </div>
      </div>

      {/* Ruleset selector + lifecycle actions */}
      <div className="card p-4 flex flex-col gap-3">
        <div className="flex flex-wrap items-center gap-3">
          <label className="text-xs font-medium text-slate-600">Ruleset</label>
          <select
            className="input w-64 text-sm"
            value={selectedId}
            onChange={(e) => selectConfig(e.target.value)}
            disabled={configsLoading}
          >
            <option value="">— Select a ruleset —</option>
            {configs?.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name} · {c.scoring_mode === 'binary' ? 'Binary' : 'Standard'}
                {c.active ? ' · active' : ''}
              </option>
            ))}
          </select>

          <button
            className="btn-primary"
            onClick={() => {
              setCreating((v) => !v);
              setDuplicating(false);
            }}
          >
            <Plus className="w-4 h-4" />
            New ruleset
          </button>

          {hasSelection && (
            <div className="flex flex-wrap items-center gap-2 ml-auto">
              {!currentConfig!.active && (
                <button
                  className="btn-secondary"
                  onClick={() => setActive.mutate()}
                  disabled={setActive.isPending}
                  title="Make this the ruleset the optimizer uses by default"
                >
                  <CheckCircle2 className="w-4 h-4" />
                  Set Active
                </button>
              )}
              <button
                className="btn-secondary"
                onClick={() => {
                  setDuplicating((v) => !v);
                  setCreating(false);
                }}
                title="Save the current rules as a separate copy"
              >
                <Copy className="w-4 h-4" />
                Save as copy
              </button>
              {(configs?.length ?? 0) > 1 && (
                <button
                  className="btn-secondary text-red-700"
                  onClick={() => setDeleteOpen(true)}
                  disabled={deleteConfig.isPending}
                  title="Delete this ruleset"
                >
                  <Trash2 className="w-4 h-4" />
                  Delete
                </button>
              )}
            </div>
          )}
        </div>

        {/* New ruleset from scratch */}
        {creating && (
          <div className="flex flex-col gap-3 border-t border-slate-100 pt-3">
            <p className="text-xs font-semibold text-slate-600">Create a new ruleset</p>
            <div className="flex flex-wrap items-end gap-4">
              <div className="flex flex-col gap-1">
                <label className="label">Name</label>
                <input
                  className="input text-sm w-64"
                  placeholder="e.g. Office Pool 2026"
                  value={newName}
                  autoFocus
                  onChange={(e) => setNewName(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && handleCreate()}
                />
              </div>
              <div className="flex flex-col gap-1">
                <label className="label">Scoring type (fixed once created)</label>
                <div className="inline-flex rounded-lg border border-slate-200 overflow-hidden">
                  <button
                    type="button"
                    className={`px-3 py-2 text-sm ${
                      newMode === 'standard'
                        ? 'bg-red-700 text-white'
                        : 'bg-white text-slate-600 hover:bg-slate-50'
                    }`}
                    onClick={() => setNewMode('standard')}
                  >
                    Standard
                  </button>
                  <button
                    type="button"
                    className={`px-3 py-2 text-sm border-l border-slate-200 ${
                      newMode === 'binary'
                        ? 'bg-red-700 text-white'
                        : 'bg-white text-slate-600 hover:bg-slate-50'
                    }`}
                    onClick={() => setNewMode('binary')}
                  >
                    Binary
                  </button>
                </div>
              </div>
              <button
                className="btn-primary"
                onClick={handleCreate}
                disabled={createConfig.isPending}
              >
                <Plus className="w-4 h-4" />
                {createConfig.isPending ? 'Creating…' : 'Create ruleset'}
              </button>
              <button
                className="btn-secondary"
                onClick={() => {
                  setCreating(false);
                  setNewName('');
                }}
              >
                Cancel
              </button>
            </div>
            <p className="text-xs text-slate-500">
              {newMode === 'binary' ? (
                <>
                  <strong>Binary</strong> rulesets award points for a correct result and
                  for the correct total goals, independently. Comes with default point
                  values you can tune after creating.
                </>
              ) : (
                <>
                  <strong>Standard</strong> rulesets award the single highest-value
                  matching rule per match. Comes pre-loaded with the default World Cup
                  rules, which you can edit or disable.
                </>
              )}
            </p>
          </div>
        )}

        {/* Save as copy */}
        {duplicating && hasSelection && (
          <div className="flex flex-wrap items-center gap-2 border-t border-slate-100 pt-3">
            <input
              className="input text-sm w-64"
              placeholder="Name for the copy"
              value={copyName}
              autoFocus
              onChange={(e) => setCopyName(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleSaveCopy()}
            />
            <button
              className="btn-primary"
              onClick={handleSaveCopy}
              disabled={duplicateConfig.isPending}
            >
              <Save className="w-4 h-4" />
              {duplicateConfig.isPending ? 'Saving…' : 'Save copy'}
            </button>
            <button
              className="btn-secondary"
              onClick={() => {
                setDuplicating(false);
                setCopyName('');
              }}
            >
              Cancel
            </button>
            <span className="text-xs text-slate-400">
              Copies this ruleset (type, settings &amp; rules) into a new one.
            </span>
          </div>
        )}
      </div>

      {/* Empty state — nothing selected */}
      {!hasSelection && !creating && (
        <div className="card p-10 flex flex-col items-center text-center gap-3">
          <ListChecks className="w-10 h-10 text-slate-200" />
          {noConfigs ? (
            <>
              <p className="text-sm font-medium text-slate-700">No rulesets yet</p>
              <p className="text-xs text-slate-500 max-w-md">
                Create your first ruleset to define how predictions earn points. The
                optimizer runs the ruleset you choose on the Optimizer page.
              </p>
              <button
                className="btn-primary mt-1"
                onClick={() => setCreating(true)}
              >
                <Plus className="w-4 h-4" />
                New ruleset
              </button>
            </>
          ) : (
            <>
              <p className="text-sm font-medium text-slate-700">No ruleset selected</p>
              <p className="text-xs text-slate-500 max-w-md">
                Pick a ruleset above to view and edit its scoring, or create a new one.
              </p>
            </>
          )}
        </div>
      )}

      {/* Selected ruleset editor */}
      {hasSelection && (
        <>
          {/* Ruleset summary header */}
          <div className="card p-4 flex flex-wrap items-center gap-3">
            <h3 className="text-base font-bold text-slate-800">{currentConfig!.name}</h3>
            <ModeBadge mode={scoringMode} />
            {currentConfig!.active && (
              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-semibold bg-emerald-100 text-emerald-700">
                <CheckCircle2 className="w-3 h-3" />
                Active
              </span>
            )}
            <span className="text-xs text-slate-400 ml-auto">
              {isBinary
                ? 'Binary scoring — the rule table does not apply.'
                : 'Standard scoring — highest matching rule wins per match.'}
            </span>
          </div>

          {/* Binary point configuration */}
          {isBinary && (
            <div className="card p-4 flex flex-col gap-3">
              <h3 className="text-sm font-semibold text-slate-700">Binary Points</h3>
              <p className="text-xs text-slate-500">
                A prediction earns these two awards independently: the result points for a
                correct outcome (home win, draw or away win), plus the total-goals points
                when the predicted total (home + away) matches.
              </p>
              <div className="flex flex-wrap items-center gap-6">
                <label className="flex items-center gap-2 text-sm text-slate-600">
                  Correct result
                  <input
                    key={`result-${currentConfig!.id}`}
                    type="number"
                    step="0.5"
                    className="w-20 text-right input font-mono text-sm"
                    defaultValue={currentConfig!.binary_result_points}
                    onBlur={(e) => {
                      const v = parseFloat(e.target.value);
                      if (!isNaN(v) && v !== currentConfig!.binary_result_points) {
                        updateConfig.mutate({ binary_result_points: v });
                      }
                    }}
                  />
                </label>
                <label className="flex items-center gap-2 text-sm text-slate-600">
                  Correct total goals
                  <input
                    key={`total-${currentConfig!.id}`}
                    type="number"
                    step="0.5"
                    className="w-20 text-right input font-mono text-sm"
                    defaultValue={currentConfig!.binary_total_goals_points}
                    onBlur={(e) => {
                      const v = parseFloat(e.target.value);
                      if (!isNaN(v) && v !== currentConfig!.binary_total_goals_points) {
                        updateConfig.mutate({ binary_total_goals_points: v });
                      }
                    }}
                  />
                </label>
              </div>
            </div>
          )}

          {/* Standard mode: editable rule tables split by phase */}
          {!isBinary && (
            <>
              <div className="flex items-center justify-end gap-2">
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

              {rulesLoading ? (
                <div className="card p-8 text-center text-slate-400">Loading rules...</div>
              ) : rules ? (
                <>
                  <div>
                    <h3 className="text-sm font-semibold text-slate-700 mb-2">
                      Group Stage Rules
                    </h3>
                    <EditableScoringTable
                      rules={rules.filter((r) => r.phase === 'group')}
                      onChange={handleChange}
                      loading={updateRule.isPending}
                    />
                  </div>
                  <div>
                    <h3 className="text-sm font-semibold text-slate-700 mb-2">
                      Knockout Stage Rules
                    </h3>
                    <p className="text-xs text-slate-500 mb-2">
                      Applied to round-of-32, round-of-16, quarter-finals, semi-finals, and
                      finals. The last two rules are exclusive to knockout matches.
                    </p>
                    <EditableScoringTable
                      rules={rules.filter((r) => r.phase === 'knockout')}
                      onChange={handleChange}
                      loading={updateRule.isPending}
                    />
                  </div>
                </>
              ) : null}
            </>
          )}
        </>
      )}

      <ConfirmDialog
        open={resetOpen}
        title="Reset Scoring Rules"
        message="This will reset all scoring rules to their defaults for this ruleset. Any custom changes will be lost."
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
        title="Delete Ruleset"
        message={`This will permanently delete the ruleset "${currentConfig?.name ?? ''}" and its scoring rules. This cannot be undone.`}
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
