'use client';

import { useEffect, useState } from 'react';
import { WifiOff } from 'lucide-react';
import { useTranslation } from '@/i18n/provider';

/**
 * Says, plainly, that the connection is gone.
 *
 * WHY THIS IS NOT DECORATION
 * --------------------------
 * Once the app loads offline it becomes indistinguishable from the online app.
 * Same layout, same numbers, same confidence. A farmer reading a recommendation
 * has no way to tell that the price behind it is a recording rather than this
 * morning's mandi rate.
 *
 * Every other honesty control in this codebase — the provisional-agronomy
 * warning, the price basis, the thirty-year-normal caveat — exists so a number
 * cannot pass for something it is not. Loading offline without saying so would
 * undo all of them at once.
 *
 * `navigator.onLine` is a weak signal: it reports true for a phone attached to
 * a tower with no route to the internet. It is used here to EXPLAIN, never to
 * decide whether to attempt a request. The API client always tries the network
 * first regardless of what this says.
 */
export function OfflineBanner() {
  const t = useTranslation();
  const [offline, setOffline] = useState(false);

  useEffect(() => {
    // Read after mount, not during render: the server has no navigator, and
    // reading it during render would be a hydration mismatch.
    const sync = () => setOffline(navigator.onLine === false);
    sync();

    window.addEventListener('online', sync);
    window.addEventListener('offline', sync);
    return () => {
      window.removeEventListener('online', sync);
      window.removeEventListener('offline', sync);
    };
  }, []);

  if (!offline) return null;

  return (
    <div
      role="status"
      aria-live="polite"
      className="no-print flex items-center justify-center gap-2 bg-amber-100 px-4 py-2 text-sm text-amber-900"
    >
      <WifiOff className="h-4 w-4 shrink-0" aria-hidden />
      <span>{t('offline.banner')}</span>
    </div>
  );
}
