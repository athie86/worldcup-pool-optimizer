import { AlertTriangle, CheckCircle } from 'lucide-react';
import type { Diagnostics } from '../types';
import { FitQualityBadge } from './FitQualityBadge';
import { ScoreHeatmap } from './ScoreHeatmap';
import { ExpectedPointsHeatmap } from './ExpectedPointsHeatmap';

interface DiagnosticsPanelProps {
  diagnostics: Diagnostics;
  homeTeam?: string;
  awayTeam?: string;
  recommendedScore?: { home: number; away: number };
}

export function DiagnosticsPanel({
  diagnostics,
  homeTeam = 'Home',
  awayTeam = 'Away',
  recommendedScore,
}: DiagnosticsPanelProps) {
  return (
    <div className="flex flex-col gap-6">
      {/* Lambda Summary */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <div className="card p-4 flex flex-col gap-1">
          <span className="text-xs text-slate-500">λ Home ({homeTeam})</span>
          <span className="text-xl font-mono font-bold text-slate-800">
            {diagnostics.lambda_home.toFixed(3)}
          </span>
        </div>
        <div className="card p-4 flex flex-col gap-1">
          <span className="text-xs text-slate-500">λ Away ({awayTeam})</span>
          <span className="text-xl font-mono font-bold text-slate-800">
            {diagnostics.lambda_away.toFixed(3)}
          </span>
        </div>
        <div className="card p-4 flex flex-col gap-1">
          <span className="text-xs text-slate-500">Total Exp. Goals</span>
          <span className="text-xl font-mono font-bold text-slate-800">
            {diagnostics.total_expected_goals.toFixed(3)}
          </span>
        </div>
        <div className="card p-4 flex flex-col gap-1">
          <span className="text-xs text-slate-500">Fit Status</span>
          <FitQualityBadge status={diagnostics.fit_status} />
          <span className="text-xs font-mono text-slate-500 mt-1">RMSE {diagnostics.rmse.toFixed(4)}</span>
        </div>
      </div>

      {/* Market vs Model */}
      {diagnostics.rows.length > 0 && (
        <div className="card overflow-hidden">
          <div className="px-4 py-3 border-b border-slate-100">
            <h3 className="text-sm font-semibold text-slate-700">Market vs Model Calibration</h3>
          </div>
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-slate-50 border-b border-slate-100">
                <th className="px-4 py-2 text-left text-xs font-semibold text-slate-500">Target</th>
                <th className="px-4 py-2 text-right text-xs font-semibold text-slate-500">Market</th>
                <th className="px-4 py-2 text-right text-xs font-semibold text-slate-500">Model</th>
                <th className="px-4 py-2 text-right text-xs font-semibold text-slate-500">Error</th>
              </tr>
            </thead>
            <tbody>
              {diagnostics.rows.map((row, i) => (
                <tr key={i} className="border-b border-slate-50 hover:bg-slate-50/50">
                  <td className="px-4 py-2 text-slate-700">{row.target}</td>
                  <td className="px-4 py-2 text-right font-mono text-slate-600">
                    {(row.market * 100).toFixed(1)}%
                  </td>
                  <td className="px-4 py-2 text-right font-mono text-slate-600">
                    {(row.model * 100).toFixed(1)}%
                  </td>
                  <td
                    className={`px-4 py-2 text-right font-mono ${
                      Math.abs(row.error) > 0.05
                        ? 'text-red-600 font-semibold'
                        : Math.abs(row.error) > 0.02
                        ? 'text-amber-600'
                        : 'text-green-700'
                    }`}
                  >
                    {row.error > 0 ? '+' : ''}
                    {(row.error * 100).toFixed(1)}%
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Heatmaps */}
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
        <div className="card p-4">
          <ScoreHeatmap
            matrix={diagnostics.score_matrix}
            title="Score Probability Matrix"
            highlightCell={
              recommendedScore
                ? { row: recommendedScore.home, col: recommendedScore.away }
                : undefined
            }
          />
        </div>
        {diagnostics.expected_points_matrix && (
          <div className="card p-4">
            <ExpectedPointsHeatmap
              matrix={diagnostics.expected_points_matrix}
              title="Expected Points Matrix"
              highlightCell={
                recommendedScore
                  ? { row: recommendedScore.home, col: recommendedScore.away }
                  : undefined
              }
            />
          </div>
        )}
      </div>

      {/* Warnings */}
      {diagnostics.warnings.length > 0 && (
        <div className="card p-4">
          <h3 className="text-sm font-semibold text-amber-700 mb-2 flex items-center gap-2">
            <AlertTriangle className="w-4 h-4" />
            Warnings ({diagnostics.warnings.length})
          </h3>
          <ul className="space-y-1">
            {diagnostics.warnings.map((w, i) => (
              <li key={i} className="text-sm text-amber-800 flex items-start gap-2">
                <span className="mt-0.5 shrink-0">•</span>
                {w}
              </li>
            ))}
          </ul>
        </div>
      )}

      {diagnostics.warnings.length === 0 && (
        <div className="flex items-center gap-2 text-sm text-green-700">
          <CheckCircle className="w-4 h-4" />
          No warnings
        </div>
      )}
    </div>
  );
}
