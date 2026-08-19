'use client';

import Link from 'next/link';
import { Sprout } from 'lucide-react';
import { useTranslation } from '@/i18n/provider';
import { LanguageSwitcher } from './language-switcher';
import { OfflineBanner } from './offline-banner';

export function AppShell({ children }: { children: React.ReactNode }) {
  const t = useTranslation();

  return (
    <div className="flex min-h-dvh flex-col">
      {/* Sits on the dark canvas rather than on a bar of its own: a solid
          header would cut the decorative field in half at the top of every
          page. A hairline and a blur are enough to separate it. */}
      <header className="sticky top-0 z-30 border-b border-white/10 bg-[hsl(155_42%_11%_/_0.72)] backdrop-blur-md">
        <div className="container flex h-16 items-center justify-between gap-3">
          <Link href="/" className="group flex items-center gap-2.5 font-semibold">
            <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-emerald-400 to-green-600 shadow-lg shadow-emerald-950/40 transition-transform group-hover:scale-105">
              <Sprout className="h-5 w-5 text-white" aria-hidden />
            </span>
            <span className="on-canvas text-lg tracking-tight">{t('app.name')}</span>
          </Link>
          <LanguageSwitcher />
        </div>
      </header>

      {/* Above the content, not tucked in a corner: once the app loads offline
          it looks exactly like the online app, and every number on the page
          quietly becomes older than it appears. */}
      <OfflineBanner />

      <main className="container flex-1 py-6">{children}</main>

      <footer className="mt-8 border-t border-white/10 py-5">
        <div className="container on-canvas-muted text-xs">{t('app.disclaimer')}</div>
      </footer>
    </div>
  );
}
