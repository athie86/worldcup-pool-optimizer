import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { AppShell } from './components/AppShell';
import { ProtectedRoute } from './components/ProtectedRoute';
import { ToastProvider } from './components/Toast';
import LoginPage from './pages/LoginPage';
import DashboardPage from './pages/DashboardPage';
import MatchesPage from './pages/MatchesPage';
import OptimizerPage from './pages/OptimizerPage';
import ScoringRulesPage from './pages/ScoringRulesPage';
import OddsOverridesPage from './pages/OddsOverridesPage';
import DiagnosticsPage from './pages/DiagnosticsPage';
import ExportsPage from './pages/ExportsPage';
import SettingsPage from './pages/SettingsPage';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      staleTime: 30_000,
    },
  },
});

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route
              element={
                <ProtectedRoute>
                  <AppShell />
                </ProtectedRoute>
              }
            >
              <Route path="/" element={<DashboardPage />} />
              <Route path="/matches" element={<MatchesPage />} />
              <Route path="/optimizer" element={<OptimizerPage />} />
              <Route path="/scoring-rules" element={<ScoringRulesPage />} />
              <Route path="/odds-overrides" element={<OddsOverridesPage />} />
              <Route path="/diagnostics" element={<DiagnosticsPage />} />
              <Route path="/exports" element={<ExportsPage />} />
              <Route path="/settings" element={<SettingsPage />} />
            </Route>
          </Routes>
        </BrowserRouter>
      </ToastProvider>
    </QueryClientProvider>
  );
}
