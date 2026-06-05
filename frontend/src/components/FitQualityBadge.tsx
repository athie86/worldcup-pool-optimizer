import clsx from 'clsx';

interface FitQualityBadgeProps {
  status: string;
  className?: string;
}

const FIT_MAP: Record<string, { label: string; className: string }> = {
  good: { label: 'Good', className: 'bg-green-100 text-green-800' },
  acceptable: { label: 'Acceptable', className: 'bg-amber-100 text-amber-800' },
  weak: { label: 'Weak', className: 'bg-orange-100 text-orange-800' },
  incomplete: { label: 'Incomplete', className: 'bg-red-100 text-red-800' },
  fit_failed: { label: 'Fit Failed', className: 'bg-red-100 text-red-800' },
  pending: { label: 'Pending', className: 'bg-slate-100 text-slate-600' },
};

export function FitQualityBadge({ status, className }: FitQualityBadgeProps) {
  const config = FIT_MAP[status.toLowerCase()] ?? {
    label: status.replace(/_/g, ' '),
    className: 'bg-slate-100 text-slate-600',
  };

  return (
    <span
      className={clsx(
        'inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium',
        config.className,
        className
      )}
    >
      {config.label}
    </span>
  );
}
