'use client';

import { useEffect } from 'react';

/**
 * Registers the service worker in public/sw.js.
 *
 * Registration is deferred until after `load`. The worker's whole job is the
 * SECOND visit; racing it against first paint would slow down the only visit
 * where it contributes nothing.
 *
 * Skipped in development, where a cache-first worker serves yesterday's bundle
 * and makes you doubt your own edits. That confusion costs more than the
 * feature is worth before deployment.
 */
export function ServiceWorkerRegistration() {
  useEffect(() => {
    if (process.env.NODE_ENV !== 'production') return;
    if (typeof navigator === 'undefined' || !('serviceWorker' in navigator)) return;

    const register = () => {
      navigator.serviceWorker.register('/sw.js').catch((error) => {
        // A failed registration means no offline support, not a broken app.
        // architecture.md principle 2 applies to our own features too.
        console.warn('[sw] registration failed; continuing online-only', error);
      });
    };

    if (document.readyState === 'complete') {
      register();
    } else {
      window.addEventListener('load', register, { once: true });
      return () => window.removeEventListener('load', register);
    }
  }, []);

  return null;
}
