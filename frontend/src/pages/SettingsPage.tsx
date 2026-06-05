import { useState, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Save, Plus, X } from 'lucide-react';
import { api } from '../api/client';
import type { AppSettings } from '../types';
import { useToastContext } from '../components/Toast';

const TIMEZONES = [
  'UTC',
  'US/Eastern',
  'US/Central',
  'US/Mountain',
  'US/Pacific',
  'Europe/London',
  'Europe/Madrid',
  'Europe/Paris',
  'America/Mexico_City',
  'America/Sao_Paulo',
  'America/Buenos_Aires',
];

export default function SettingsPage() {
  const { toast } = useToastContext();
  const qc = useQueryClient();

  const { data: settings, isLoading } = useQuery({
    queryKey: ['settings'],
    queryFn: () => api.get<AppSettings>('/settings'),
  });

  const [form, setForm] = useState<AppSettings>({
    odds_sport_key: 'soccer_fifa_world_cup',
    odds_regions: ['us', 'eu'],
    odds_bookmakers: ['pinnacle', 'bet365', 'draftkings'],
    refresh_hour_utc: 6,
    refresh_timezone: 'UTC',
    auto_run_optimizer: false,
  });

  const [newBookmaker, setNewBookmaker] = useState('');
  const [newRegion, setNewRegion] = useState('');

  useEffect(() => {
    if (settings) setForm(settings);
  }, [settings]);

  const saveMutation = useMutation({
    mutationFn: () => api.put<AppSettings>('/settings', form),
    onSuccess: () => {
      toast.success('Settings saved successfully');
      qc.invalidateQueries({ queryKey: ['settings'] });
    },
    onError: (e: Error) => toast.error(`Save failed: ${e.message}`),
  });

  const handleChange = <K extends keyof AppSettings>(key: K, value: AppSettings[K]) => {
    setForm((prev) => ({ ...prev, [key]: value }));
  };

  const addBookmaker = () => {
    const b = newBookmaker.trim().toLowerCase();
    if (!b || form.odds_bookmakers.includes(b)) return;
    handleChange('odds_bookmakers', [...form.odds_bookmakers, b]);
    setNewBookmaker('');
  };

  const removeBookmaker = (b: string) => {
    handleChange('odds_bookmakers', form.odds_bookmakers.filter((x) => x !== b));
  };

  const addRegion = () => {
    const r = newRegion.trim().toLowerCase();
    if (!r || form.odds_regions.includes(r)) return;
    handleChange('odds_regions', [...form.odds_regions, r]);
    setNewRegion('');
  };

  const removeRegion = (r: string) => {
    handleChange('odds_regions', form.odds_regions.filter((x) => x !== r));
  };

  if (isLoading) {
    return <div className="card p-8 text-center text-slate-400">Loading settings...</div>;
  }

  return (
    <div className="flex flex-col gap-5 max-w-2xl">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold text-slate-800">Settings</h2>
          <p className="text-sm text-slate-500 mt-0.5">Configure odds provider and schedule settings</p>
        </div>
        <button
          className="btn-primary"
          onClick={() => saveMutation.mutate()}
          disabled={saveMutation.isPending}
        >
          <Save className="w-4 h-4" />
          {saveMutation.isPending ? 'Saving...' : 'Save Settings'}
        </button>
      </div>

      {/* Odds Provider */}
      <div className="card p-5 flex flex-col gap-4">
        <h3 className="text-sm font-semibold text-slate-700 border-b border-slate-100 pb-2">
          Odds Provider
        </h3>

        <div>
          <label className="label" htmlFor="sport-key">
            Sport Key
          </label>
          <input
            id="sport-key"
            className="input font-mono"
            value={form.odds_sport_key}
            onChange={(e) => handleChange('odds_sport_key', e.target.value)}
          />
          <p className="text-xs text-slate-400 mt-1">
            The odds-api.com sport key for fetching odds.
          </p>
        </div>

        {/* Regions */}
        <div>
          <label className="label">Regions</label>
          <div className="flex flex-wrap gap-2 mb-2">
            {form.odds_regions.map((r) => (
              <span
                key={r}
                className="inline-flex items-center gap-1 px-2.5 py-1 bg-blue-100 text-blue-800 text-xs rounded-full font-medium"
              >
                {r}
                <button
                  className="hover:text-blue-600"
                  onClick={() => removeRegion(r)}
                >
                  <X className="w-3 h-3" />
                </button>
              </span>
            ))}
          </div>
          <div className="flex gap-2">
            <input
              className="input flex-1 text-sm"
              placeholder="Add region (e.g. us, eu, uk)"
              value={newRegion}
              onChange={(e) => setNewRegion(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && addRegion()}
            />
            <button className="btn-secondary" onClick={addRegion}>
              <Plus className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Bookmakers */}
        <div>
          <label className="label">Bookmakers</label>
          <div className="flex flex-wrap gap-2 mb-2">
            {form.odds_bookmakers.map((b) => (
              <span
                key={b}
                className="inline-flex items-center gap-1 px-2.5 py-1 bg-slate-100 text-slate-700 text-xs rounded-full font-medium font-mono"
              >
                {b}
                <button
                  className="hover:text-red-600"
                  onClick={() => removeBookmaker(b)}
                >
                  <X className="w-3 h-3" />
                </button>
              </span>
            ))}
          </div>
          <div className="flex gap-2">
            <input
              className="input flex-1 text-sm font-mono"
              placeholder="Add bookmaker key (e.g. pinnacle)"
              value={newBookmaker}
              onChange={(e) => setNewBookmaker(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && addBookmaker()}
            />
            <button className="btn-secondary" onClick={addBookmaker}>
              <Plus className="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>

      {/* Schedule */}
      <div className="card p-5 flex flex-col gap-4">
        <h3 className="text-sm font-semibold text-slate-700 border-b border-slate-100 pb-2">
          Refresh Schedule
        </h3>

        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="label" htmlFor="refresh-hour">
              Refresh Hour (UTC)
            </label>
            <input
              id="refresh-hour"
              type="number"
              min={0}
              max={23}
              className="input font-mono"
              value={form.refresh_hour_utc}
              onChange={(e) => handleChange('refresh_hour_utc', parseInt(e.target.value) || 0)}
            />
            <p className="text-xs text-slate-400 mt-1">Hour of day (0-23) in UTC</p>
          </div>

          <div>
            <label className="label" htmlFor="timezone">
              Display Timezone
            </label>
            <select
              id="timezone"
              className="input text-sm"
              value={form.refresh_timezone}
              onChange={(e) => handleChange('refresh_timezone', e.target.value)}
            >
              {TIMEZONES.map((tz) => (
                <option key={tz} value={tz}>
                  {tz}
                </option>
              ))}
            </select>
          </div>
        </div>
      </div>

      {/* Automation */}
      <div className="card p-5 flex flex-col gap-4">
        <h3 className="text-sm font-semibold text-slate-700 border-b border-slate-100 pb-2">
          Automation
        </h3>
        <label className="flex items-center gap-3 cursor-pointer">
          <div className="relative">
            <input
              type="checkbox"
              className="sr-only"
              checked={form.auto_run_optimizer}
              onChange={(e) => handleChange('auto_run_optimizer', e.target.checked)}
            />
            <div
              className={`w-10 h-6 rounded-full transition-colors ${
                form.auto_run_optimizer ? 'bg-red-700' : 'bg-slate-300'
              }`}
            >
              <div
                className={`absolute top-1 w-4 h-4 rounded-full bg-white shadow transition-transform ${
                  form.auto_run_optimizer ? 'translate-x-5' : 'translate-x-1'
                }`}
              />
            </div>
          </div>
          <div>
            <span className="text-sm font-medium text-slate-700">Auto-run Optimizer</span>
            <p className="text-xs text-slate-400">
              Automatically run the optimizer after each odds refresh
            </p>
          </div>
        </label>
      </div>
    </div>
  );
}
