import { api } from './client';
import type { ModelRun, Diagnostics, MatchRecommendation } from '../types';

export interface RunOptimizerPayload {
  pool_config_id: string;
  odds_snapshot_id?: string;
  top_n?: number;
  match_ids?: string[];
}

export const modelRunsApi = {
  list: () => api.get<ModelRun[]>('/model-runs'),

  get: (id: string) => api.get<ModelRun>(`/model-runs/${id}`),

  run: (payload: RunOptimizerPayload) => api.post<ModelRun>('/model-runs', payload),

  getRecommendations: (runId: string) =>
    api.get<MatchRecommendation[]>(`/model-runs/${runId}/recommendations`),

  getDiagnostics: (runId: string, matchId: string) =>
    api.get<Diagnostics>(`/model-runs/${runId}/diagnostics/${matchId}`),

  latest: () => api.get<ModelRun>('/model-runs/latest'),
};
