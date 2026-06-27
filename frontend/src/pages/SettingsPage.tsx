import { useQuery } from '@tanstack/react-query';
import { api } from '../api/client';
import { Info } from 'lucide-react';

interface AppSettings {
  odds_sport_key: string;
  odds_regions: string[];
  odds_bookmakers: string[];
  refresh_hour_utc: number;
  refresh_timezone: string;
  auto_run_optimizer: boolean;
  odds_api_key_configured: boolean;
}

export default function SettingsPage() {
  const { data: settings, isLoading } = useQuery({
    queryKey: ['settings'],
    queryFn: () => api.get<AppSettings>('/settings'),
  });

  if (isLoading) {
    return <div className="card p-8 text-center text-slate-400">Loading settings...</div>;
  }

  return (
    <div className="flex flex-col gap-5 max-w-2xl">
      <div>
        <h2 className="text-xl font-bold text-slate-800">Settings</h2>
        <p className="text-sm text-slate-500 mt-0.5">Current odds provider configuration</p>
      </div>

      <div className="flex items-start gap-3 px-4 py-3 bg-blue-50 border border-blue-200 rounded-lg text-sm text-blue-800">
        <Info className="w-4 h-4 mt-0.5 flex-shrink-0" />
        <span>
          Settings are configured via environment variables. To change them, update your{' '}
          <code className="font-mono bg-blue-100 px-1 rounded">.env</code> file and restart the
          backend.
        </span>
      </div>

      <div className="card p-5 flex flex-col gap-4">
        <h3 className="text-sm font-semibold text-slate-700 border-b border-slate-100 pb-2">
          Odds Provider
        </h3>

        <div>
          <label className="label">API Key</label>
          <div className={`input font-mono text-sm ${settings?.odds_api_key_configured ? 'text-green-700' : 'text-red-600'}`}>
            {settings?.odds_api_key_configured ? '••••••••••••••••••••••••• (configured)' : 'Not configured — set ODDS_API_KEY'}
          </div>
        </div>

        <div>
          <label className="label">Sport Key</label>
          <div className="input font-mono text-sm text-slate-600 bg-slate-50">
            {settings?.odds_sport_key ?? '—'}
          </div>
        </div>

        <div>
          <label className="label">Regions</label>
          <div className="flex flex-wrap gap-2">
            {settings?.odds_regions.map((r) => (
              <span key={r} className="inline-flex items-center px-2.5 py-1 bg-blue-100 text-blue-800 text-xs rounded-full font-medium">
                {r}
              </span>
            ))}
          </div>
        </div>

        <div>
          <label className="label">Bookmakers</label>
          <div className="flex flex-wrap gap-2">
            {settings?.odds_bookmakers && settings.odds_bookmakers.length > 0 ? (
              settings.odds_bookmakers.map((b) => (
                <span key={b} className="inline-flex items-center px-2.5 py-1 bg-slate-100 text-slate-700 text-xs rounded-full font-medium font-mono">
                  {b}
                </span>
              ))
            ) : (
              <span className="text-xs text-slate-400">All bookmakers (none filtered)</span>
            )}
          </div>
        </div>
      </div>

      <div className="card p-5 flex flex-col gap-4">
        <h3 className="text-sm font-semibold text-slate-700 border-b border-slate-100 pb-2">
          Schedule
        </h3>
        <div className="grid grid-cols-2 gap-4 text-sm">
          <div>
            <div className="label">Refresh Hour (local)</div>
            <div className="input font-mono text-slate-600 bg-slate-50">{settings?.refresh_hour_utc ?? '—'}</div>
          </div>
          <div>
            <div className="label">Timezone</div>
            <div className="input text-slate-600 bg-slate-50">{settings?.refresh_timezone ?? '—'}</div>
          </div>
        </div>
      </div>

      <div className="card p-5 flex flex-col gap-4">
        <h3 className="text-sm font-semibold text-slate-700 border-b border-slate-100 pb-2">
          Automation
        </h3>
        <div className="flex items-center gap-3">
          <div className={`w-10 h-6 rounded-full ${settings?.auto_run_optimizer ? 'bg-red-700' : 'bg-slate-300'} relative flex-shrink-0`}>
            <div className={`absolute top-1 w-4 h-4 rounded-full bg-white shadow transition-transform ${settings?.auto_run_optimizer ? 'translate-x-5' : 'translate-x-1'}`} />
          </div>
          <div>
            <span className="text-sm font-medium text-slate-700">Auto-run Optimizer</span>
            <p className="text-xs text-slate-400">{settings?.auto_run_optimizer ? 'Enabled' : 'Disabled'}</p>
          </div>
        </div>
      </div>
    </div>
  );
}
