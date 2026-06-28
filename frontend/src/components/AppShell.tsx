import { useEffect, useState } from 'react';
import { Outlet, useLocation } from 'react-router-dom';
import { X } from 'lucide-react';
import { SidebarNav } from './SidebarNav';
import { TopBar } from './TopBar';
import { BrandMark } from './BrandMark';

/** Inner contents of the navy sidebar, shared by the desktop rail and the mobile drawer. */
function SidebarBody({ onNavigate }: { onNavigate?: () => void }) {
  return (
    <>
      {/* Logo area */}
      <div className="h-14 flex items-center gap-3 px-4 border-b border-white/10 shrink-0">
        <BrandMark className="w-9 h-9 rounded-lg shrink-0 shadow-sm" />
        <div className="flex flex-col leading-tight">
          <span className="text-white text-xs font-semibold tracking-wide">WORLD CUP</span>
          <span className="text-yellow-400 text-xs font-medium">Pool Optimizer</span>
        </div>
      </div>

      {/* Nav */}
      <div className="flex-1 overflow-y-auto py-2">
        <SidebarNav onNavigate={onNavigate} />
      </div>

      {/* Footer */}
      <div className="px-4 py-3 border-t border-white/10 shrink-0">
        <span className="text-xs text-slate-500">FIFA World Cup 2026</span>
      </div>
    </>
  );
}

export function AppShell() {
  const [drawerOpen, setDrawerOpen] = useState(false);
  const { pathname } = useLocation();

  // Close the drawer whenever the route changes.
  useEffect(() => {
    setDrawerOpen(false);
  }, [pathname]);

  // Close on Escape and lock body scroll while the drawer is open.
  useEffect(() => {
    if (!drawerOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setDrawerOpen(false);
    };
    document.addEventListener('keydown', onKey);
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.removeEventListener('keydown', onKey);
      document.body.style.overflow = prevOverflow;
    };
  }, [drawerOpen]);

  return (
    <div className="flex h-screen w-full overflow-hidden bg-slate-100">
      {/* Desktop sidebar */}
      <aside
        className="hidden lg:flex w-60 shrink-0 flex-col"
        style={{ backgroundColor: 'var(--color-navy-950)' }}
      >
        <SidebarBody />
      </aside>

      {/* Mobile drawer + backdrop */}
      <div
        className={`lg:hidden fixed inset-0 z-40 bg-black/50 transition-opacity duration-200 ${
          drawerOpen ? 'opacity-100' : 'pointer-events-none opacity-0'
        }`}
        onClick={() => setDrawerOpen(false)}
        aria-hidden="true"
      />
      <aside
        className={`lg:hidden fixed inset-y-0 left-0 z-50 w-72 max-w-[85vw] flex flex-col pl-safe-l shadow-xl transition-transform duration-200 ease-out ${
          drawerOpen ? 'translate-x-0' : '-translate-x-full'
        }`}
        style={{ backgroundColor: 'var(--color-navy-950)' }}
        role="dialog"
        aria-modal="true"
        aria-label="Main navigation"
      >
        <button
          type="button"
          className="absolute top-3 right-3 z-10 inline-flex h-9 w-9 items-center justify-center rounded-lg text-slate-300 hover:bg-white/10 hover:text-white"
          onClick={() => setDrawerOpen(false)}
          aria-label="Close navigation"
        >
          <X className="w-5 h-5" />
        </button>
        <SidebarBody onNavigate={() => setDrawerOpen(false)} />
      </aside>

      {/* Main content */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        <TopBar onOpenDrawer={() => setDrawerOpen(true)} drawerOpen={drawerOpen} />
        <main className="flex-1 overflow-y-auto p-4 sm:p-6 pb-safe-b">
          <div className="max-w-[1440px] mx-auto">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  );
}
