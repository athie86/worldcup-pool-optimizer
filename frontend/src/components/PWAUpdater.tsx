import { useEffect } from 'react';
import { useRegisterSW } from 'virtual:pwa-register/react';
import { useToastContext } from './Toast';

/**
 * Registers the service worker and surfaces its lifecycle through the existing
 * toast system: a confirmation once the app is cached for offline use, and an
 * auto-applied refresh when a new build is available. Rendered inside
 * ToastProvider so it can use the toast context.
 */
export function PWAUpdater() {
  const { toast } = useToastContext();
  const {
    needRefresh: [needRefresh, setNeedRefresh],
    offlineReady: [offlineReady, setOfflineReady],
    updateServiceWorker,
  } = useRegisterSW();

  useEffect(() => {
    if (offlineReady) {
      toast.info('App ready to work offline');
      setOfflineReady(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [offlineReady]);

  useEffect(() => {
    if (needRefresh) {
      toast.info('New version available — updating…');
      updateServiceWorker(true);
      setNeedRefresh(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [needRefresh]);

  return null;
}
