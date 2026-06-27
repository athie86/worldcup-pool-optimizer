import { api } from './client';
import type { Match, DashboardStats, ImportSummary } from '../types';

export interface MatchListParams {
  stage?: string;
  status?: string;
  page?: number;
  page_size?: number;
}

export interface PaginatedMatches {
  items: Match[];
  total: number;
  page: number;
  page_size: number;
}

export interface CreateMatchPayload {
  stage: string;
  group_label?: string;
  home_team_id?: string;
  away_team_id?: string;
  home_placeholder?: string;
  away_placeholder?: string;
  kickoff_at?: string;
  venue?: string;
  city?: string;
  country?: string;
  scoring_basis: string;
}

export const matchesApi = {
  list: (params?: MatchListParams) => {
    const qs = new URLSearchParams();
    if (params?.stage) qs.set('stage', params.stage);
    if (params?.status) qs.set('status', params.status);
    if (params?.page !== undefined) qs.set('page', String(params.page));
    if (params?.page_size !== undefined) qs.set('page_size', String(params.page_size));
    const query = qs.toString();
    return api.get<PaginatedMatches>(`/matches${query ? `?${query}` : ''}`);
  },

  get: (id: string) => api.get<Match>(`/matches/${id}`),

  create: (payload: CreateMatchPayload) => api.post<Match>('/matches', payload),

  update: (id: string, payload: Partial<CreateMatchPayload>) =>
    api.put<Match>(`/matches/${id}`, payload),

  delete: (id: string) => api.delete<void>(`/matches/${id}`),

  importSchedule: async (file: File): Promise<ImportSummary> => {
    const form = new FormData();
    form.append('file', file);
    const res = await fetch('/api/matches/import', {
      method: 'POST',
      credentials: 'include',
      body: form,
    });
    const text = await res.text();
    let data: unknown;
    try {
      data = JSON.parse(text);
    } catch {
      data = undefined;
    }
    if (!res.ok) {
      const detail =
        data && typeof data === 'object' && 'detail' in data
          ? String((data as { detail: unknown }).detail)
          : text || 'Import failed';
      throw new Error(detail);
    }
    return data as ImportSummary;
  },

  importProviderSchedule: () =>
    api.post<ImportSummary>('/matches/import-provider-schedule', {}),

  dashboardStats: () => api.get<DashboardStats>('/dashboard/stats'),
};
