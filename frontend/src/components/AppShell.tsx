import { Outlet } from 'react-router-dom';
import { SidebarNav } from './SidebarNav';
import { TopBar } from './TopBar';
import { BrandMark } from './BrandMark';

export function AppShell() {
  return (
    <div className="flex h-screen w-full overflow-hidden bg-slate-100">
      {/* Sidebar */}
      <aside
        className="w-60 shrink-0 flex flex-col"
        style={{ backgroundColor: 'var(--color-navy-950)' }}
      >
        {/* Logo area */}
        <div className="h-14 flex items-center gap-3 px-4 border-b border-white/10">
          <BrandMark className="w-9 h-9 rounded-lg shrink-0 shadow-sm" />
          <div className="flex flex-col leading-tight">
            <span className="text-white text-xs font-semibold tracking-wide">WORLD CUP</span>
            <span className="text-yellow-400 text-xs font-medium">Pool Optimizer</span>
          </div>
        </div>

        {/* Nav */}
        <div className="flex-1 overflow-y-auto py-2">
          <SidebarNav />
        </div>

        {/* Footer */}
        <div className="px-4 py-3 border-t border-white/10">
          <span className="text-xs text-slate-500">FIFA World Cup 2026</span>
        </div>
      </aside>

      {/* Main content */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        <TopBar />
        <main className="flex-1 overflow-y-auto p-6">
          <div className="max-w-[1440px] mx-auto">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  );
}
