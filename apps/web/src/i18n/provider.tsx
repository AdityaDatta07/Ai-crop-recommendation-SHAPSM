'use client';

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import {
  DEFAULT_LOCALE,
  interpolate,
  lookup,
  LOCALES,
  MESSAGES,
  type Locale,
} from './index';

const STORAGE_KEY = 'crop:locale';

interface I18nValue {
  locale: Locale;
  setLocale: (locale: Locale) => void;
  t: (key: string, values?: Record<string, string | number>) => string;
}

const I18nContext = createContext<I18nValue | null>(null);

function isLocale(value: string | null): value is Locale {
  return value !== null && (LOCALES as readonly string[]).includes(value);
}

export function I18nProvider({ children }: { children: React.ReactNode }) {
  // Always start at the default so the server and first client render agree.
  // Reading localStorage during render would produce a hydration mismatch.
  const [locale, setLocaleState] = useState<Locale>(DEFAULT_LOCALE);

  useEffect(() => {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    if (isLocale(stored)) {
      setLocaleState(stored);
      return;
    }
    // No stored preference: follow the browser, which on an Indian handset set
    // to Hindi is a better first guess than English.
    if (navigator.language?.toLowerCase().startsWith('hi')) setLocaleState('hi');
  }, []);

  useEffect(() => {
    document.documentElement.lang = locale;
  }, [locale]);

  const setLocale = useCallback((next: Locale) => {
    setLocaleState(next);
    try {
      window.localStorage.setItem(STORAGE_KEY, next);
    } catch {
      // Private mode. The choice just will not persist.
    }
  }, []);

  const t = useCallback(
    (key: string, values?: Record<string, string | number>) =>
      interpolate(lookup(MESSAGES[locale], key), values),
    [locale],
  );

  const value = useMemo(() => ({ locale, setLocale, t }), [locale, setLocale, t]);

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n(): I18nValue {
  const context = useContext(I18nContext);
  if (context === null) throw new Error('useI18n must be used inside I18nProvider');
  return context;
}

/** Convenience for components that only need the translate function. */
export function useTranslation() {
  return useI18n().t;
}
