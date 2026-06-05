import clsx from 'clsx';

interface StatusBadgeProps {
  status: string;
  className?: string;
}

const STATUS_MAP: Record<string, { label: string; className: string }> = {
  scheduled: { label: 'Scheduled', className: 'bg-blue-100 text-blue-800' },
  live: { label: 'Live', className: 'bg-green-100 text-green-800 animate-pulse' },
  complete: { label: 'Complete', className: 'bg-slate-100 text-slate-700' },
  completed: { label: 'Complete', className: 'bg-slate-100 text-slate-700' },
  incomplete: { label: 'Incomplete', className: 'bg-amber-100 text-amber-800' },
  pending: { label: 'Pending', className: 'bg-yellow-100 text-yellow-800' },
  running: { label: 'Running', className: 'bg-blue-100 text-blue-800' },
  failed: { label: 'Failed', className: 'bg-red-100 text-red-800' },
  fit_failed: { label: 'Fit Failed', className: 'bg-red-100 text-red-800' },
  success: { label: 'Success', className: 'bg-green-100 text-green-800' },
  cancelled: { label: 'Cancelled', className: 'bg-slate-100 text-slate-500' },
  has_overrides: { label: 'Override', className: 'bg-purple-100 text-purple-800' },
  no_odds: { label: 'No Odds', className: 'bg-orange-100 text-orange-800' },
};

export function StatusBadge({ status, className }: StatusBadgeProps) {
  const config = STATUS_MAP[status.toLowerCase()] ?? {
    label: status.replace(/_/g, ' '),
    className: 'bg-slate-100 text-slate-600',
  };

  return (
    <span
      className={clsx(
        'inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium capitalize',
        config.className,
        className
      )}
    >
      {config.label}
    </span>
  );
}
