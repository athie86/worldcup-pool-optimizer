import { useEffect, useState } from 'react';
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
} from 'lucide-react';
import { poolConfigsApi } from '../api/poolConfigs';
import { EditableScoringTable } from '../components/EditableScoringTable';
import { ConfirmDialog } from '../components/ConfirmDialog';
import { useToastContext } from '../components/Toast';
import type { CombineMode, KnockoutScoringBasis, PoolConfig } from '../types';

const BASIS_LABELS: Record<KnockoutScoringBasis, string> = {
  ninety_minutes: '90 minutes only (+ stoppage)',
  ninety_minutes_extra_time: '90 minutes + extra time',
  ninety_minutes_extra_time_penalties: '90 + extra time + penalties',
};

/** Best ⟷ Additive segmented control for one phase. */
function CombineToggle({
  value,
  onChange,
  disabled,
}: {
  value: CombineMode;
  onChange: (v: CombineMode) => void;
  disabled?: boolean;
}) {
  return (
    <div className="inline-flex rounded-lg border border-slate-200 overflow-hidden">
      {(['best', 'additive'] as CombineMode[]).map((mode) => (
        <button
          key={mode}
          type="button"
          disabled={disabled}
          className={`px-3 py-1.5 text-xs font-medium ${
            value === mode
              ? 'bg-red-700 text-white'
              : 'bg-white text-slate-600 hover:bg-slate-50'
          } ${mode === 'additive' ? 'border-l border-slate-200' : ''}`}
          onClick={() => onChange(mode)}
        >
          {mode === 'best' ? 'Best match' : 'Additive'}
        </button>
      ))}
    </div>
  );
}

export default function ScoringRulesPage() {
  const { toast } = useToastContext();
  const qc = useQueryClient();

  const [selectedId, setSelectedId] = useState('');
  const [resetOpen, setResetOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);

  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState('');

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
    enabled: hasSelection,
  });

  const createConfig = useMutation({
    mutationFn: (name: string) =>
      poolConfigsApi.create({
        name,
        description: 'Created from Scoring Rules',
        active: false,
      }),
    onSuccess: (created) => {
      toast.success(`Ruleset "${created.name}" created`);
      setCreating(false);
      setNewName('');
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
      payload: { points?: number; enabled?: boolean; config?: Record<string, unknown> | null };
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
      toast.success('Ruleset set as active');
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

  const handleChange = (
    ruleId: string,
    changes: { points?: number; enabled?: boolean; config?: Record<string, unknown> | null }
  ) => {
    // Toggles and config edits save immediately; point edits batch into "Save Changes".
    if (changes.enabled !== undefined || changes.config !== undefined) {
      updateRule.mutate({ ruleId, payload: changes });
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
    createConfig.mutate(name);
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
            A <strong>ruleset</strong> defines how predictions earn points. For each phase
            you choose a <strong>combine mode</strong> — <strong>Best match</strong> (only
            the single highest-value component scores) or <strong>Additive</strong> (every
            matching component is summed) — plus an optional per-match cap.
          </p>
          <p className="mt-1">
            Pick which ruleset to run on the Optimizer page. Hover the{' '}
            <Info className="inline w-3 h-3 -mt-0.5" /> next to any component to see exactly
            what it means with an example.
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
                {c.name}
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
                  title="Mark this ruleset active"
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
              <button
                className="btn-secondary text-red-700"
                onClick={() => setDeleteOpen(true)}
                disabled={deleteConfig.isPending}
                title="Delete this ruleset"
              >
                <Trash2 className="w-4 h-4" />
                Delete
              </button>
            </div>
          )}
        </div>

        {/* New ruleset from scratch */}
        {creating && (
          <div className="flex flex-wrap items-end gap-3 border-t border-slate-100 pt-3">
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
            <p className="w-full text-xs text-slate-500">
              New rulesets start from the full component catalog (Best match) with sensible
              default points. Tune everything below after creating.
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
                Create your first ruleset to define how predictions earn points.
              </p>
              <button className="btn-primary mt-1" onClick={() => setCreating(true)}>
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
        <RulesetEditor
          key={currentConfig!.id}
          config={currentConfig!}
          rules={rules}
          rulesLoading={rulesLoading}
          rulesSaving={updateRule.isPending}
          pendingCount={Object.keys(pendingChanges).length}
          hasPending={hasPending}
          onRename={(name) => updateConfig.mutate({ name })}
          onConfigChange={(payload) => updateConfig.mutate(payload)}
          onRuleChange={handleChange}
          onSaveAll={handleSaveAll}
          onReset={() => setResetOpen(true)}
        />
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

interface RulesetEditorProps {
  config: PoolConfig;
  rules: PoolConfig['scoring_rules'];
  rulesLoading: boolean;
  rulesSaving: boolean;
  pendingCount: number;
  hasPending: boolean;
  onRename: (name: string) => void;
  onConfigChange: (payload: Parameters<typeof poolConfigsApi.update>[1]) => void;
  onRuleChange: (
    ruleId: string,
    changes: { points?: number; enabled?: boolean; config?: Record<string, unknown> | null }
  ) => void;
  onSaveAll: () => void;
  onReset: () => void;
}

function RulesetEditor({
  config,
  rules,
  rulesLoading,
  rulesSaving,
  pendingCount,
  hasPending,
  onRename,
  onConfigChange,
  onRuleChange,
  onSaveAll,
  onReset,
}: RulesetEditorProps) {
  const [name, setName] = useState(config.name);
  useEffect(() => setName(config.name), [config.name]);

  const groupRules = (rules ?? []).filter((r) => r.phase === 'group');
  const knockoutRules = (rules ?? []).filter((r) => r.phase === 'knockout');

  return (
    <>
      {/* Ruleset summary header */}
      <div className="card p-4 flex flex-col gap-3">
        <div className="flex flex-wrap items-center gap-3">
          <input
            className="input text-base font-bold text-slate-800 w-72"
            value={name}
            onChange={(e) => setName(e.target.value)}
            onBlur={() => {
              const trimmed = name.trim();
              if (trimmed && trimmed !== config.name) onRename(trimmed);
              else setName(config.name);
            }}
            title="Rename this ruleset"
          />
          {config.active && (
            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-semibold bg-emerald-100 text-emerald-700">
              <CheckCircle2 className="w-3 h-3" />
              Active
            </span>
          )}
        </div>

        {/* Pool-level settings */}
        <div className="flex flex-wrap items-end gap-6 border-t border-slate-100 pt-3">
          <label className="flex flex-col gap-1 text-xs font-medium text-slate-600">
            Knockout scoring basis
            <select
              className="input text-sm w-64"
              value={config.knockout_scoring_basis}
              onChange={(e) =>
                onConfigChange({ knockout_scoring_basis: e.target.value as KnockoutScoringBasis })
              }
              title="The match time scope knockouts are scored on. 90-minutes-only pools earn no advance/penalty bonus."
            >
              {Object.entries(BASIS_LABELS).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1 text-xs font-medium text-slate-600">
            <span className="flex items-center gap-1">
              Picks lock (minutes before kickoff)
              <span title="Informational only — how long before kickoff picks close in this pool. Not enforced by the optimizer.">
                <Info className="w-3 h-3 text-slate-400" />
              </span>
            </span>
            <input
              type="number"
              min={0}
              placeholder="unset"
              className="input text-sm w-32 font-mono"
              defaultValue={config.pick_lock_minutes_before ?? ''}
              onBlur={(e) => {
                const v = e.target.value.trim();
                const next = v === '' ? null : parseInt(v, 10);
                if (next !== (config.pick_lock_minutes_before ?? null)) {
                  onConfigChange({ pick_lock_minutes_before: next });
                }
              }}
            />
          </label>
        </div>
      </div>

      {/* Save / reset actions */}
      <div className="flex items-center justify-end gap-2">
        <button className="btn-secondary" onClick={onReset} disabled={rulesSaving}>
          <RotateCcw className="w-4 h-4" />
          Reset to Defaults
        </button>
        <button className="btn-primary" onClick={onSaveAll} disabled={!hasPending || rulesSaving}>
          <Save className="w-4 h-4" />
          Save Changes {hasPending ? `(${pendingCount})` : ''}
        </button>
      </div>

      {rulesLoading ? (
        <div className="card p-8 text-center text-slate-400">Loading rules...</div>
      ) : (
        <>
          <PhaseSection
            title="Group Stage"
            combineMode={config.group_combine_mode}
            cap={config.group_cap}
            onCombineChange={(v) => onConfigChange({ group_combine_mode: v })}
            onCapChange={(v) => onConfigChange({ group_cap: v })}
            rules={groupRules}
            rulesSaving={rulesSaving}
            onRuleChange={onRuleChange}
          />
          <PhaseSection
            title="Knockout Stage"
            subtitle="Round-of-32 through the final. Two knockout-only bonuses (advance, penalty winner) are added on top of the score — see the highlighted section below the table."
            combineMode={config.knockout_combine_mode}
            cap={config.knockout_cap}
            onCombineChange={(v) => onConfigChange({ knockout_combine_mode: v })}
            onCapChange={(v) => onConfigChange({ knockout_cap: v })}
            rules={knockoutRules}
            rulesSaving={rulesSaving}
            onRuleChange={onRuleChange}
          />
        </>
      )}
    </>
  );
}

interface PhaseSectionProps {
  title: string;
  subtitle?: string;
  combineMode: CombineMode;
  cap?: number | null;
  onCombineChange: (v: CombineMode) => void;
  onCapChange: (v: number | null) => void;
  rules: NonNullable<PoolConfig['scoring_rules']>;
  rulesSaving: boolean;
  onRuleChange: (
    ruleId: string,
    changes: { points?: number; enabled?: boolean; config?: Record<string, unknown> | null }
  ) => void;
}

function PhaseSection({
  title,
  subtitle,
  combineMode,
  cap,
  onCombineChange,
  onCapChange,
  rules,
  rulesSaving,
  onRuleChange,
}: PhaseSectionProps) {
  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-3">
        <h3 className="text-sm font-semibold text-slate-700">{title}</h3>
        <CombineToggle value={combineMode} onChange={onCombineChange} disabled={rulesSaving} />
        <label className="flex items-center gap-1.5 text-xs text-slate-500">
          Per-match cap
          <input
            type="number"
            min={0}
            placeholder="none"
            className="w-20 text-right input !py-1 font-mono text-xs"
            defaultValue={cap ?? ''}
            key={`cap-${title}-${cap ?? ''}`}
            onBlur={(e) => {
              const v = e.target.value.trim();
              const next = v === '' ? null : parseFloat(v);
              if (next !== (cap ?? null)) onCapChange(next);
            }}
            title="Maximum points a single match can score in this phase. Leave blank for no cap."
          />
        </label>
      </div>
      {subtitle && <p className="text-xs text-slate-500">{subtitle}</p>}
      <EditableScoringTable
        rules={rules}
        onChange={onRuleChange}
        loading={rulesSaving}
        combineMode={combineMode}
      />
    </div>
  );
}
