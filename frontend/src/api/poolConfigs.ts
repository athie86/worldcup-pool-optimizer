import { api } from './client';
import type {
  PoolConfig,
  ScoringRule,
  CombineMode,
  KnockoutScoringBasis,
} from '../types';

export interface CreatePoolConfigPayload {
  name: string;
  description?: string;
  default_top_n?: number;
  candidate_max_goals?: number;
  ranking_metric?: string;
  margin_removal_method?: string;
  group_combine_mode?: CombineMode;
  knockout_combine_mode?: CombineMode;
  group_cap?: number | null;
  knockout_cap?: number | null;
  knockout_scoring_basis?: KnockoutScoringBasis;
  pick_lock_minutes_before?: number | null;
  active?: boolean;
}

export interface DuplicatePoolConfigPayload {
  name: string;
  description?: string;
  active?: boolean;
}

export interface UpdateScoringRulePayload {
  points?: number;
  enabled?: boolean;
  config?: Record<string, unknown> | null;
}

export const poolConfigsApi = {
  list: () => api.get<PoolConfig[]>('/pool-configs'),

  get: (id: string) => api.get<PoolConfig>(`/pool-configs/${id}`),

  create: (payload: CreatePoolConfigPayload) =>
    api.post<PoolConfig>('/pool-configs', payload),

  update: (id: string, payload: Partial<CreatePoolConfigPayload>) =>
    api.put<PoolConfig>(`/pool-configs/${id}`, payload),

  delete: (id: string) => api.delete<void>(`/pool-configs/${id}`),

  duplicate: (id: string, payload: DuplicatePoolConfigPayload) =>
    api.post<PoolConfig>(`/pool-configs/${id}/duplicate`, payload),

  setActive: (id: string) => api.post<PoolConfig>(`/pool-configs/${id}/activate`),

  getScoringRules: (configId: string) =>
    api.get<ScoringRule[]>(`/pool-configs/${configId}/scoring-rules`),

  updateScoringRule: (
    configId: string,
    ruleId: string,
    payload: UpdateScoringRulePayload
  ) => api.patch<ScoringRule>(`/pool-configs/${configId}/scoring-rules/${ruleId}`, payload),

  resetScoringRules: (configId: string) =>
    api.post<ScoringRule[]>(`/pool-configs/${configId}/scoring-rules/reset`),
};
