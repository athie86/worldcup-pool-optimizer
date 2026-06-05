import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { authApi } from '../api/auth';

export function useAuth() {
  const qc = useQueryClient();

  const { data, isLoading } = useQuery({
    queryKey: ['auth', 'me'],
    queryFn: authApi.me,
    retry: false,
  });

  const login = useMutation({
    mutationFn: (password: string) => authApi.login(password),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['auth'] }),
  });

  const logout = useMutation({
    mutationFn: authApi.logout,
    onSuccess: () => {
      qc.clear();
      window.location.href = '/login';
    },
  });

  return {
    user: data,
    isAuthenticated: data?.authenticated ?? false,
    isLoading,
    login,
    logout,
  };
}
