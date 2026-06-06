import { api } from './client';

export interface AuthMe {
  authenticated: boolean;
  username: string | null;
}

export const authApi = {
  me: () => api.get<AuthMe>('/auth/me'),

  login: (password: string) =>
    api.post<{ authenticated: boolean; username: string | null }>('/auth/login', {
      username: 'admin',
      password,
    }),

  logout: () => api.post<void>('/auth/logout'),
};
