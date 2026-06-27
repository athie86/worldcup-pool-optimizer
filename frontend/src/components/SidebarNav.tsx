import React from 'react';
import { NavLink } from 'react-router-dom';
import {
  LayoutDashboard,
  Calendar,
  Target,
  List,
  BarChart2,
  Activity,
  BookOpen,
  Download,
  Settings,
} from 'lucide-react';
import clsx from 'clsx';

interface NavItem {
  to: string;
  label: string;
  icon: React.ReactNode;
}

const NAV_ITEMS: NavItem[] = [
  { to: '/', label: 'Dashboard', icon: <LayoutDashboard className="w-4.5 h-4.5" /> },
  { to: '/matches', label: 'Matches', icon: <Calendar className="w-4.5 h-4.5" /> },
  { to: '/optimizer', label: 'Optimizer', icon: <Target className="w-4.5 h-4.5" /> },
  { to: '/scoring-rules', label: 'Scoring Rules', icon: <List className="w-4.5 h-4.5" /> },
  { to: '/odds-overrides', label: 'Odds & Overrides', icon: <BarChart2 className="w-4.5 h-4.5" /> },
  { to: '/diagnostics', label: 'Diagnostics', icon: <Activity className="w-4.5 h-4.5" /> },
  { to: '/model-docs', label: 'Prediction Model', icon: <BookOpen className="w-4.5 h-4.5" /> },
  { to: '/exports', label: 'Exports', icon: <Download className="w-4.5 h-4.5" /> },
  { to: '/settings', label: 'Settings', icon: <Settings className="w-4.5 h-4.5" /> },
];

export function SidebarNav() {
  return (
    <nav className="flex flex-col gap-0.5 px-3 py-2">
      {NAV_ITEMS.map((item) => (
        <NavLink
          key={item.to}
          to={item.to}
          end={item.to === '/'}
          className={({ isActive }) =>
            clsx(
              'flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all',
              isActive
                ? 'bg-red-700 text-white shadow-sm'
                : 'text-slate-300 hover:bg-white/10 hover:text-white'
            )
          }
        >
          {item.icon}
          {item.label}
        </NavLink>
      ))}
    </nav>
  );
}
