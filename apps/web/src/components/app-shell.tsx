'use client';

import Link from 'next/link';
import { Sprout } from 'lucide-react';
import { useTranslation } from '@/i18n/provider';
import { LanguageSwitcher } from './language-switcher';

export function AppShell({ children }: { children: React.ReactNode }) {
  const t = useTranslation();

  return (
    <div className="flex min-h-dvh flex-col">
      <header className="border-b border-border bg-background">
        <div className="container flex h-14 items-center justify-between gap-3">
          <Link href="/" className="flex items-center gap-2 font-semibold">
            <Sprout className="h-5 w-5 text-primary" aria-hidden />
            {t('app.name')}
          </Link>
          <LanguageSwitcher />
        </div>
      </header>

      <main className="container flex-1 py-6">{children}</main>

      <footer className="border-t border-border py-4">
        <div className="container text-xs text-muted-foreground">{t('app.disclaimer')}</div>
      </footer>
    </div>
  );
}
