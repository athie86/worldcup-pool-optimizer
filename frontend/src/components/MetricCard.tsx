import React from 'react';
import clsx from 'clsx';

interface MetricCardProps {
  title: string;
  value: string | number;
  subtitle?: string;
  status?: 'good' | 'warning' | 'danger' | 'neutral';
  icon?: React.ReactNode;
}

const STATUS_DOT: Record<string, string> = {
  good: 'bg-green-500',
  warning: 'bg-amber-500',
  danger: 'bg-red-500',
  neutral: 'bg-slate-400',
};

const STATUS_VALUE: Record<string, string> = {
  good: 'text-green-700',
  warning: 'text-amber-700',
  danger: 'text-red-700',
  neutral: 'text-slate-800',
};

export function MetricCard({ title, value, subtitle, status = 'neutral', icon }: MetricCardProps) {
  return (
    <div className="card p-5 flex flex-col gap-3">
      <div className="flex items-start justify-between">
        <span className="text-sm font-medium text-slate-500">{title}</span>
        <div className="flex items-center gap-2">
          {status !== 'neutral' && (
            <span
              className={clsx('w-2.5 h-2.5 rounded-full', STATUS_DOT[status])}
            />
          )}
          {icon && <span className="text-slate-400">{icon}</span>}
        </div>
      </div>
      <div className="flex items-end justify-between">
        <span
          className={clsx(
            'text-2xl font-bold tabular-nums',
            STATUS_VALUE[status]
          )}
        >
          {value}
        </span>
        {subtitle && (
          <span className="text-xs text-slate-400 mb-1">{subtitle}</span>
        )}
      </div>
    </div>
  );
}
