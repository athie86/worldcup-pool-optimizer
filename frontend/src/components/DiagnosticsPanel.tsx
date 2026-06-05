import { useState } from 'react';
import { AlertTriangle, CheckCircle, ToggleLeft, ToggleRight } from 'lucide-react';
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

function fmt(v: number | undefined, decimals = 4) {
  if (v === undefined || v === null) return '—';
  return v.toFixed(decimals);
}

function fmtPct(v: number | undefined, decimals = 1) {
  if (v === undefined || v === null) return '—';
  return `${(v * 100).toFixed(decimals)}%`;
}

function errorColor(abs: number) {
  if (abs > 0.05) return 'text-red-600 font-semibold';
  if (abs > 0.02) return 'text-amber-600';
  return 'text-green-700';
}

export function DiagnosticsPanel({
  diagnostics,
  homeTeam = 'Home',
  awayTeam = 'Away',
  recommendedScore,
}: DiagnosticsPanelProps) {
  const [showPriorMatrix, setShowPriorMatrix] = useState(false);

  const activeMatrix = showPriorMatrix && diagnostics.prior_matrix
    ? diagnostics.prior_matrix
    : diagnostics.score_matrix;

  const hasPrior = !!diagnostics.prior_matrix;
  const hasPriorRows = diagnostics.rows.some(r => r.prior !== undefined);

  return (
    <div className="flex flex-col gap-6">
      {/* ── Model parameter summary ──────────────────────────────────────── */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <div className="card p-4 flex flex-col gap-1">
          <span className="text-xs text-slate-500">λ Home ({homeTeam})</span>
          <span className="text-xl font-mono font-bold text-slate-800">
            {fmt(diagnostics.lambda_home, 3)}
          </span>
        </div>
        <div className="card p-4 flex flex-col gap-1">
          <span className="text-xs text-slate-500">λ Away ({awayTeam})</span>
          <span className="text-xl font-mono font-bold text-slate-800">
            {fmt(diagnostics.lambda_away, 3)}
          </span>
        </div>
        <div className="card p-4 flex flex-col gap-1">
          <span className="text-xs text-slate-500">ρ (Dixon-Coles)</span>
          <span className="text-xl font-mono font-bold text-slate-800">
            {diagnostics.rho !== undefined ? fmt(diagnostics.rho, 3) : '—'}
          </span>
        </div>
        <div className="card p-4 flex flex-col gap-1">
          <span className="text-xs text-slate-500">Fit Status</span>
          <FitQualityBadge status={diagnostics.fit_status} />
          <span className="text-xs font-mono text-slate-500 mt-1">
            RMSE {fmt(diagnostics.rmse, 4)}
          </span>
        </div>
      </div>

      {/* ── Calibration quality metrics ──────────────────────────────────── */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <div className="card p-4 flex flex-col gap-1">
          <span className="text-xs text-slate-500">Prior RMSE</span>
          <span className="font-mono font-semibold text-slate-700">
            {fmt(diagnostics.prior_rmse, 4)}
          </span>
          <span className="text-xs text-slate-400">DC before calibration</span>
        </div>
        <div className="card p-4 flex flex-col gap-1">
          <span className="text-xs text-slate-500">Calibrated RMSE</span>
          <span className="font-mono font-semibold text-slate-700">
            {fmt(diagnostics.rmse, 4)}
          </span>
          <span className="text-xs text-slate-400">After entropy calibration</span>
        </div>
        <div className="card p-4 flex flex-col gap-1">
          <span className="text-xs text-slate-500">Max Single Error</span>
          <span className="font-mono font-semibold text-slate-700">
            {fmtPct(diagnostics.max_single_market_error)}
          </span>
          <span className="text-xs text-slate-400">Worst market deviation</span>
        </div>
        <div className="card p-4 flex flex-col gap-1">
          <span className="text-xs text-slate-500">KL from Prior</span>
          <span className="font-mono font-semibold text-slate-700">
            {fmt(diagnostics.kl_divergence_from_prior, 4)}
          </span>
          <span className="text-xs text-slate-400">
            Tail mass {fmtPct(diagnostics.tail_mass_before_normalization)}
          </span>
        </div>
      </div>

      {/* ── Market vs Model calibration table ────────────────────────────── */}
      {diagnostics.rows.length > 0 && (
        <div className="card overflow-hidden">
          <div className="px-4 py-3 border-b border-slate-100">
            <h3 className="text-sm font-semibold text-slate-700">
              Market vs Model Calibration
            </h3>
            <p className="text-xs text-slate-400 mt-0.5">
              Dixon-Coles prior vs entropy-calibrated final matrix
            </p>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-slate-50 border-b border-slate-100">
                  <th className="px-4 py-2 text-left text-xs font-semibold text-slate-500">
                    Target
                  </th>
                  <th className="px-4 py-2 text-right text-xs font-semibold text-slate-500">
                    Market
                  </th>
                  {hasPriorRows && (
                    <th className="px-4 py-2 text-right text-xs font-semibold text-slate-400">
                      Prior (DC)
                    </th>
                  )}
                  <th className="px-4 py-2 text-right text-xs font-semibold text-slate-500">
                    Calibrated
                  </th>
                  <th className="px-4 py-2 text-right text-xs font-semibold text-slate-500">
                    Error
                  </th>
                </tr>
              </thead>
              <tbody>
                {diagnostics.rows.map((row, i) => (
                  <tr key={i} className="border-b border-slate-50 hover:bg-slate-50/50">
                    <td className="px-4 py-2 text-slate-700">{row.target}</td>
                    <td className="px-4 py-2 text-right font-mono text-slate-600">
                      {fmtPct(row.market)}
                    </td>
                    {hasPriorRows && (
                      <td className="px-4 py-2 text-right font-mono text-slate-400">
                        {row.prior !== undefined ? fmtPct(row.prior) : '—'}
                      </td>
                    )}
                    <td className="px-4 py-2 text-right font-mono text-slate-600">
                      {fmtPct(row.model)}
                    </td>
                    <td
                      className={`px-4 py-2 text-right font-mono ${errorColor(Math.abs(row.error))}`}
                    >
                      {row.error > 0 ? '+' : ''}
                      {fmtPct(row.error)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* ── Heatmaps ─────────────────────────────────────────────────────── */}
      <div className="flex flex-col gap-4">
        {/* Matrix toggle */}
        {hasPrior && (
          <div className="flex items-center gap-3">
            <span className="text-sm text-slate-600">Score matrix:</span>
            <button
              onClick={() => setShowPriorMatrix(false)}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                !showPriorMatrix
                  ? 'bg-navy-900 text-white'
                  : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
              }`}
            >
              Calibrated (final)
            </button>
            <button
              onClick={() => setShowPriorMatrix(true)}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                showPriorMatrix
                  ? 'bg-slate-600 text-white'
                  : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
              }`}
            >
              DC Prior
            </button>
            {showPriorMatrix ? (
              <ToggleLeft className="w-4 h-4 text-slate-400" />
            ) : (
              <ToggleRight className="w-4 h-4 text-amber-500" />
            )}
          </div>
        )}

        <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
          <div className="card p-4">
            <ScoreHeatmap
              matrix={activeMatrix}
              title={
                showPriorMatrix && hasPrior
                  ? 'Score Probability — DC Prior'
                  : 'Score Probability — Calibrated'
              }
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
      </div>

      {/* ── Warnings ─────────────────────────────────────────────────────── */}
      {diagnostics.warnings.length > 0 ? (
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
      ) : (
        <div className="flex items-center gap-2 text-sm text-green-700">
          <CheckCircle className="w-4 h-4" />
          No warnings
        </div>
      )}
    </div>
  );
}
