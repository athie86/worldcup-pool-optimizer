import { api } from './client';
import type { ModelRun, Diagnostics, MatchRecommendation } from '../types';

export interface RunOptimizerPayload {
  pool_config_id: string;
  odds_snapshot_id?: string;
  top_n?: number;
  match_ids?: string[];
  /** "v1" (legacy Dixon-Coles) or "v2" (market-calibrated full-grid model). */
  model_version?: string;
}

export const modelRunsApi = {
  list: () => api.get<ModelRun[]>('/model-runs'),

  get: (id: string) => api.get<ModelRun>(`/model-runs/${id}`),

  run: ({ model_version, ...payload }: RunOptimizerPayload) =>
    api.post<ModelRun>('/model-runs', {
      ...payload,
      // The backend selects the model from parameters.model_version.
      parameters: model_version ? { model_version } : undefined,
    }),

  getRecommendations: (runId: string) =>
    api.get<MatchRecommendation[]>(`/model-runs/${runId}/recommendations`),

  getDiagnostics: (runId: string, matchId: string) =>
    api.get<Diagnostics>(`/model-runs/${runId}/diagnostics/${matchId}`),

  latest: () => api.get<ModelRun>('/model-runs/latest'),
};
