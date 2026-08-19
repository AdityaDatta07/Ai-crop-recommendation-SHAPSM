'use client';

import Link from 'next/link';
import { WifiOff } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useTranslation } from '@/i18n/provider';

/**
 * The last resort: a route the service worker could not serve from cache.
 *
 * Reached only when the network is down AND the requested page was never
 * cached. Its whole job is to say what is still available rather than leaving
 * a farmer looking at the browser's dinosaur, which tells them nothing about
 * the advisory they already have on the phone.
 */
export default function OfflinePage() {
  const t = useTranslation();

  return (
    <div className="mx-auto max-w-md py-12 text-center">
      <WifiOff className="on-canvas-muted mx-auto h-10 w-10" aria-hidden />
      <h1 className="on-canvas mt-4 text-xl font-semibold">{t('offline.title')}</h1>
      <p className="on-canvas-muted mt-2 text-sm">{t('offline.body')}</p>

      <div className="mt-6 flex flex-wrap justify-center gap-2">
        <Button onClick={() => window.location.reload()}>{t('offline.retry')}</Button>
        <Link href="/">
          <Button variant="outline">{t('offline.home')}</Button>
        </Link>
      </div>
    </div>
  );
}
