import { api } from './client';
import type { OddsSnapshot, MatchOdds, ManualOverride, OddsRefreshResult } from '../types';

export interface CreateOverridePayload {
  market_key: string;
  line?: number;
  outcome_type: string;
  price_decimal: number;
  reason?: string;
}

export const oddsApi = {
  // Snapshots
  listSnapshots: () => api.get<OddsSnapshot[]>('/odds/snapshots'),

  getSnapshot: (id: string) => api.get<OddsSnapshot>(`/odds/snapshots/${id}`),

  // Manual odds refresh. Body is optional; the backend uses configured defaults.
  triggerRefresh: () => api.post<OddsRefreshResult>('/odds/refresh', {}),

  // Match odds
  getMatchOdds: (matchId: string) => api.get<MatchOdds>(`/odds/matches/${matchId}`),

  // Overrides
  listOverrides: (matchId: string) =>
    api.get<ManualOverride[]>(`/odds/matches/${matchId}/overrides`),

  createOverride: (matchId: string, payload: CreateOverridePayload) =>
    api.post<ManualOverride>(`/odds/matches/${matchId}/overrides`, payload),

  updateOverride: (matchId: string, overrideId: string, payload: Partial<CreateOverridePayload>) =>
    api.put<ManualOverride>(`/odds/matches/${matchId}/overrides/${overrideId}`, payload),

  deleteOverride: (matchId: string, overrideId: string) =>
    api.delete<void>(`/odds/matches/${matchId}/overrides/${overrideId}`),

  toggleOverride: (matchId: string, overrideId: string, enabled: boolean) =>
    api.patch<ManualOverride>(`/odds/matches/${matchId}/overrides/${overrideId}`, { enabled }),
};
