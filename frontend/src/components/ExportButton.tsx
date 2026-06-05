import { useState, useRef, useEffect } from 'react';
import { Download, ChevronDown } from 'lucide-react';
import clsx from 'clsx';

interface ExportButtonProps {
  onExport: (format: 'csv' | 'xlsx') => void;
  loading?: boolean;
  className?: string;
}

export function ExportButton({ onExport, loading, className }: ExportButtonProps) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handler(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  return (
    <div ref={ref} className={clsx('relative inline-block', className)}>
      <button
        className="btn-secondary flex items-center gap-1.5"
        onClick={() => setOpen((o) => !o)}
        disabled={loading}
      >
        <Download className="w-4 h-4" />
        Export
        <ChevronDown className="w-3.5 h-3.5" />
      </button>
      {open && (
        <div className="absolute right-0 mt-1 w-44 bg-white border border-slate-200 rounded-xl shadow-lg py-1 z-20">
          <button
            className="w-full text-left px-4 py-2 text-sm text-slate-700 hover:bg-slate-50 flex items-center gap-2"
            onClick={() => { onExport('csv'); setOpen(false); }}
          >
            <Download className="w-4 h-4 text-slate-400" />
            Export CSV
          </button>
          <button
            className="w-full text-left px-4 py-2 text-sm text-slate-700 hover:bg-slate-50 flex items-center gap-2"
            onClick={() => { onExport('xlsx'); setOpen(false); }}
          >
            <Download className="w-4 h-4 text-slate-400" />
            Export Excel
          </button>
        </div>
      )}
    </div>
  );
}
