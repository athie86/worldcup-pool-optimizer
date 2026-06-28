import { useLocation } from 'react-router-dom';
import { LogOut, User, Menu } from 'lucide-react';
import { useAuth } from '../hooks/useAuth';

interface TopBarProps {
  onOpenDrawer?: () => void;
  drawerOpen?: boolean;
}

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

export function TopBar({ onOpenDrawer, drawerOpen }: TopBarProps) {
  const { pathname } = useLocation();
  const { user, logout } = useAuth();
  const title = PAGE_TITLES[pathname] ?? 'World Cup Pool Optimizer';

  return (
    <header className="h-14 bg-white border-b border-slate-200 flex items-center justify-between px-4 lg:px-6 shrink-0">
      <div className="flex items-center gap-1 min-w-0">
        <button
          type="button"
          className="lg:hidden -ml-2 inline-flex h-11 w-11 items-center justify-center rounded-lg text-slate-600 hover:bg-slate-100 hover:text-slate-900 transition-colors"
          onClick={onOpenDrawer}
          aria-label="Open navigation menu"
          aria-expanded={drawerOpen ?? false}
        >
          <Menu className="w-5 h-5" />
        </button>
        <h1 className="text-base font-semibold text-slate-800 truncate">{title}</h1>
      </div>
      <div className="flex items-center gap-2 sm:gap-3 shrink-0">
        <div className="flex items-center gap-2 text-sm text-slate-600">
          <User className="w-4 h-4 text-slate-400" />
          <span className="hidden sm:inline">{user?.username ?? 'Admin'}</span>
        </div>
        <button
          className="flex items-center justify-center gap-1.5 text-sm text-slate-500 hover:text-slate-800 transition-colors h-10 px-2 sm:px-3 rounded-lg hover:bg-slate-100"
          onClick={() => logout.mutate()}
          aria-label="Sign out"
        >
          <LogOut className="w-4 h-4" />
          <span className="hidden sm:inline">Sign out</span>
        </button>
      </div>
    </header>
  );
}
