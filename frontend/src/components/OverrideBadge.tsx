import clsx from 'clsx';

interface OverrideBadgeProps {
  hasOverrides: boolean;
  className?: string;
}

export function OverrideBadge({ hasOverrides, className }: OverrideBadgeProps) {
  if (!hasOverrides) return null;

  return (
    <span
      className={clsx(
        'inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-purple-100 text-purple-800',
        className
      )}
    >
      Override
    </span>
  );
}
