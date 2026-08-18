'use client';

import { Languages } from 'lucide-react';
import { useI18n } from '@/i18n/provider';
import { LOCALES, LOCALE_NAMES, type Locale } from '@/i18n';
import { cn } from '@/lib/utils';

/**
 * Two languages, so a toggle beats a dropdown - one tap instead of two, which
 * matters more than it sounds on a phone held in a field.
 */
export function LanguageSwitcher() {
  const { locale, setLocale, t } = useI18n();

  return (
    <div
      className="flex items-center gap-1 rounded-md border border-border p-0.5"
      role="group"
      aria-label={t('language.label')}
    >
      <Languages className="ml-1.5 h-4 w-4 text-muted-foreground" aria-hidden />
      {LOCALES.map((option: Locale) => (
        <button
          key={option}
          type="button"
          onClick={() => setLocale(option)}
          aria-pressed={locale === option}
          className={cn(
            'rounded px-2.5 py-1 text-sm font-medium transition-colors',
            locale === option
              ? 'bg-primary text-primary-foreground'
              : 'text-muted-foreground hover:text-foreground',
          )}
        >
          {LOCALE_NAMES[option]}
        </button>
      ))}
    </div>
  );
}
