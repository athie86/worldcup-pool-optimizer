import { api } from './client';
import type { Match, DashboardStats } from '../types';

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

  importSchedule: (file: File) => {
    const form = new FormData();
    form.append('file', file);
    return fetch('/api/matches/import', {
      method: 'POST',
      credentials: 'include',
      body: form,
    }).then((r) => r.json());
  },

  dashboardStats: () => api.get<DashboardStats>('/dashboard/stats'),
};
