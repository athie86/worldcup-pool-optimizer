import { api } from './client';
import type { ExportRecord } from '../types';

export interface CreateExportPayload {
  format: 'csv' | 'xlsx';
  model_run_id: string;
  top_n?: number;
}

export const exportsApi = {
  list: () => api.get<ExportRecord[]>('/exports'),

  create: (payload: CreateExportPayload) => api.post<ExportRecord>('/exports', payload),

  download: (id: string) => `/api/exports/${id}/download`,
};
