import React from 'react';
import {
  useReactTable,
  getCoreRowModel,
  getPaginationRowModel,
  getSortedRowModel,
  flexRender,
  type ColumnDef,
  type SortingState,
} from '@tanstack/react-table';
import { ChevronUp, ChevronDown, ChevronsUpDown, ChevronLeft, ChevronRight } from 'lucide-react';
import clsx from 'clsx';

interface DataTableProps<TData> {
  data: TData[];
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  columns: ColumnDef<TData, any>[];
  pageSize?: number;
  className?: string;
  /**
   * Optional mobile card renderer. When provided, the table is hidden below `lg`
   * and rows render as stacked cards instead — sharing the same sorted/paginated
   * row model so sorting and pagination still apply.
   */
  renderMobileCard?: (row: TData) => React.ReactNode;
}

export function DataTable<TData>({
  data,
  columns,
  pageSize = 20,
  className,
  renderMobileCard,
}: DataTableProps<TData>) {
  const [sorting, setSorting] = React.useState<SortingState>([]);

  const table = useReactTable({
    data,
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    getSortedRowModel: getSortedRowModel(),
    initialState: { pagination: { pageSize } },
  });

  const rows = table.getRowModel().rows;

  return (
    <div className={clsx('flex flex-col', className)}>
      {/* Mobile card list (only when a renderer is supplied) */}
      {renderMobileCard && (
        <div className="lg:hidden flex flex-col gap-3">
          {rows.length === 0 ? (
            <div className="px-3 py-8 text-center text-sm text-slate-400">No data available</div>
          ) : (
            rows.map((row) => (
              <div key={row.id}>{renderMobileCard(row.original)}</div>
            ))
          )}
        </div>
      )}

      <div className={clsx('overflow-x-auto scroll-touch', renderMobileCard && 'hidden lg:block')}>
        <table className="w-full text-sm border-collapse">
          <thead>
            {table.getHeaderGroups().map((hg) => (
              <tr key={hg.id} className="bg-slate-50 border-b border-slate-200">
                {hg.headers.map((header) => (
                  <th
                    key={header.id}
                    className={clsx(
                      'px-3 py-2.5 text-left text-xs font-semibold text-slate-600 whitespace-nowrap select-none',
                      header.column.getCanSort() && 'cursor-pointer hover:text-slate-900'
                    )}
                    onClick={header.column.getToggleSortingHandler()}
                  >
                    <div className="flex items-center gap-1">
                      {header.isPlaceholder
                        ? null
                        : flexRender(header.column.columnDef.header, header.getContext())}
                      {header.column.getCanSort() &&
                        (header.column.getIsSorted() === 'asc' ? (
                          <ChevronUp className="w-3.5 h-3.5 text-red-600" />
                        ) : header.column.getIsSorted() === 'desc' ? (
                          <ChevronDown className="w-3.5 h-3.5 text-red-600" />
                        ) : (
                          <ChevronsUpDown className="w-3.5 h-3.5 text-slate-300" />
                        ))}
                    </div>
                  </th>
                ))}
              </tr>
            ))}
          </thead>
          <tbody>
            {table.getRowModel().rows.length === 0 ? (
              <tr>
                <td
                  colSpan={columns.length}
                  className="px-3 py-8 text-center text-sm text-slate-400"
                >
                  No data available
                </td>
              </tr>
            ) : (
              table.getRowModel().rows.map((row, i) => (
                <tr
                  key={row.id}
                  className={clsx(
                    'border-b border-slate-100 hover:bg-slate-50 transition-colors',
                    i % 2 === 0 ? 'bg-white' : 'bg-slate-50/40'
                  )}
                >
                  {row.getVisibleCells().map((cell) => (
                    <td key={cell.id} className="px-3 py-2 text-slate-700">
                      {flexRender(cell.column.columnDef.cell, cell.getContext())}
                    </td>
                  ))}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {table.getPageCount() > 1 && (
        <div className="flex items-center justify-between px-3 py-3 border-t border-slate-100 bg-white">
          <span className="text-xs text-slate-500">
            Page {table.getState().pagination.pageIndex + 1} of {table.getPageCount()} &nbsp;·&nbsp;{' '}
            {data.length} total
          </span>
          <div className="flex items-center gap-1">
            <button
              className="btn-secondary px-2 py-1 text-xs"
              onClick={() => table.previousPage()}
              disabled={!table.getCanPreviousPage()}
            >
              <ChevronLeft className="w-4 h-4" />
            </button>
            <button
              className="btn-secondary px-2 py-1 text-xs"
              onClick={() => table.nextPage()}
              disabled={!table.getCanNextPage()}
            >
              <ChevronRight className="w-4 h-4" />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
