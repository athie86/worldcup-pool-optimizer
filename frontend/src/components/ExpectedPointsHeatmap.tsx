import clsx from 'clsx';

interface ExpectedPointsHeatmapProps {
  matrix: number[][];
  title?: string;
  highlightCell?: { row: number; col: number };
}

function goldInterpolate(t: number): string {
  // slate-100 (#F1F5F9) -> gold (#F1BF00)
  const sr = 241, sg = 245, sb = 249;
  const gr = 241, gg = 191, gb = 0;
  return `rgb(${Math.round(sr + (gr - sr) * t)},${Math.round(sg + (gg - sg) * t)},${Math.round(sb + (gb - sb) * t)})`;
}

function getTextColor(t: number): string {
  return t > 0.6 ? '#1E293B' : '#475569';
}

export function ExpectedPointsHeatmap({
  matrix,
  title = 'Expected Points',
  highlightCell,
}: ExpectedPointsHeatmapProps) {
  const rows = matrix.length;
  const cols = rows > 0 ? matrix[0].length : 0;

  const allValues = matrix.flat();
  const maxVal = Math.max(...allValues, 0.0001);

  return (
    <div className="flex flex-col gap-2">
      <span className="text-xs font-semibold text-slate-600 uppercase tracking-wide">{title}</span>
      <div className="overflow-x-auto">
        <table className="border-collapse text-xs font-mono">
          <thead>
            <tr>
              <th className="px-1.5 py-1 text-slate-400 font-normal text-right w-16">H↓ A→</th>
              {Array.from({ length: cols }, (_, j) => (
                <th key={j} className="px-1.5 py-1 text-slate-500 font-medium w-14 text-center">
                  {j}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {Array.from({ length: rows }, (_, i) => (
              <tr key={i}>
                <td className="px-1.5 py-1 text-slate-500 font-medium text-right">{i}</td>
                {Array.from({ length: cols }, (_, j) => {
                  const val = matrix[i]?.[j] ?? 0;
                  const t = maxVal > 0 ? val / maxVal : 0;
                  const isHighlight = highlightCell?.row === i && highlightCell?.col === j;
                  return (
                    <td
                      key={j}
                      className={clsx(
                        'w-14 h-10 text-center tabular-nums',
                        isHighlight && 'ring-2 ring-red-600 ring-inset'
                      )}
                      style={{
                        backgroundColor: goldInterpolate(t),
                        color: getTextColor(t),
                        position: 'relative',
                      }}
                    >
                      {val.toFixed(2)}
                      {isHighlight && (
                        <span
                          className="absolute top-0.5 right-0.5 w-2 h-2 rounded-full bg-red-600"
                          aria-hidden
                        />
                      )}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="flex items-center gap-2 text-xs text-slate-400">
        <span>Rows = Home Goals, Cols = Away Goals</span>
      </div>
    </div>
  );
}
