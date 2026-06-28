import React from 'react';
import clsx from 'clsx';

interface ScrollableTableProps {
  children: React.ReactNode;
  className?: string;
  /** When true, bleed to the container edges on mobile so the scroll area uses full width. */
  bleed?: boolean;
}

/**
 * Horizontal-scroll wrapper for dense tables that cannot reasonably reflow on small
 * screens. Provides momentum scrolling on touch devices and a right-edge fade hint
 * that content continues off-screen.
 */
export function ScrollableTable({ children, className, bleed = false }: ScrollableTableProps) {
  return (
    <div className={clsx('scroll-fade-x', bleed && '-mx-4 sm:mx-0')}>
      <div className={clsx('overflow-x-auto scroll-touch', bleed && 'px-4 sm:px-0', className)}>
        {children}
      </div>
    </div>
  );
}
