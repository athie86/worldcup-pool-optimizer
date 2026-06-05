import { useLocation } from 'react-router-dom';
import { LogOut, User } from 'lucide-react';
import { useAuth } from '../hooks/useAuth';

const PAGE_TITLES: Record<string, string> = {
  '/': 'Dashboard',
  '/matches': 'Matches',
  '/optimizer': 'Optimizer',
  '/scoring-rules': 'Scoring Rules',
  '/odds-overrides': 'Odds & Overrides',
  '/diagnostics': 'Diagnostics',
  '/exports': 'Exports',
  '/settings': 'Settings',
};

export function TopBar() {
  const { pathname } = useLocation();
  const { user, logout } = useAuth();
  const title = PAGE_TITLES[pathname] ?? 'World Cup Pool Optimizer';

  return (
    <header className="h-14 bg-white border-b border-slate-200 flex items-center justify-between px-6 shrink-0">
      <h1 className="text-base font-semibold text-slate-800">{title}</h1>
      <div className="flex items-center gap-3">
        <div className="flex items-center gap-2 text-sm text-slate-600">
          <User className="w-4 h-4 text-slate-400" />
          <span>{user?.username ?? 'Admin'}</span>
        </div>
        <button
          className="flex items-center gap-1.5 text-sm text-slate-500 hover:text-slate-800 transition-colors px-2 py-1.5 rounded-lg hover:bg-slate-100"
          onClick={() => logout.mutate()}
        >
          <LogOut className="w-4 h-4" />
          Sign out
        </button>
      </div>
    </header>
  );
}
