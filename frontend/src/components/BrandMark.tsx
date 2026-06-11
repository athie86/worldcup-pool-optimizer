import clsx from 'clsx';

interface BrandMarkProps {
  className?: string;
  size?: number;
  alt?: string;
}

export function BrandMark({ className, size, alt = 'World Cup Pool Optimizer' }: BrandMarkProps) {
  return (
    <img
      src="/mark.svg"
      alt={alt}
      width={size}
      height={size}
      className={clsx('select-none', className)}
      draggable={false}
    />
  );
}
