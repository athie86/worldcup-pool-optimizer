import clsx from 'clsx';

interface ScoreHeatmapProps {
  matrix: number[][];
  title: string;
  formatValue?: (v: number) => string;
  highlightCell?: { row: number; col: number };
}

function blueInterpolate(t: number): string {
  // t in [0,1]: 0=very light blue, 1=deep blue
  const r = Math.round(239 - t * (239 - 30));
  const g = Math.round(246 - t * (246 - 64));
  const b = Math.round(255 - t * (255 - 175));
  return `rgb(${r},${g},${b})`;
}

function getTextColor(t: number): string {
  return t > 0.5 ? '#fff' : '#1E293B';
}

export function ScoreHeatmap({
  matrix,
  title,
  formatValue = (v) => (v * 100).toFixed(1) + '%',
  highlightCell,
}: ScoreHeatmapProps) {
  // matrix[homeGoals][awayGoals]
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
                  const t = val / maxVal;
                  const isHighlight = highlightCell?.row === i && highlightCell?.col === j;
                  return (
                    <td
                      key={j}
                      className={clsx(
                        'w-14 h-10 text-center tabular-nums transition-all',
                        isHighlight && 'ring-2 ring-red-600 ring-inset'
                      )}
                      style={{
                        backgroundColor: blueInterpolate(t),
                        color: getTextColor(t),
                        position: 'relative',
                      }}
                    >
                      {formatValue(val)}
                      {isHighlight && (
                        <span
                          className="absolute top-0.5 right-0.5 w-2 h-2 rounded-full bg-yellow-400"
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
