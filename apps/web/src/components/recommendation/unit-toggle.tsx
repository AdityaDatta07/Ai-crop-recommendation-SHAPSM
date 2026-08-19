'use client';

import { createContext, useContext, useEffect, useState } from 'react';
import { cn } from '@/lib/utils';
import { useTranslation } from '@/i18n/provider';

export type AreaUnit = 'hectare' | 'acre';

const STORAGE_KEY = 'crop:area-unit';

const UnitContext = createContext<{
  unit: AreaUnit;
  setUnit: (unit: AreaUnit) => void;
}>({ unit: 'hectare', setUnit: () => {} });

/**
 * Hectare or acre.
 *
 * Both figures arrive from the API already computed; this only chooses which to
 * display. No conversion happens in the browser, because the moment money is
 * multiplied client-side there are two places a wrong number can come from.
 */
export function UnitProvider({ children }: { children: React.ReactNode }) {
  const [unit, setUnitState] = useState<AreaUnit>('hectare');

  useEffect(() => {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    if (stored === 'acre' || stored === 'hectare') setUnitState(stored);
  }, []);

  const setUnit = (next: AreaUnit) => {
    setUnitState(next);
    try {
      window.localStorage.setItem(STORAGE_KEY, next);
    } catch {
      /* private mode; the choice just will not persist */
    }
  };

  return <UnitContext.Provider value={{ unit, setUnit }}>{children}</UnitContext.Provider>;
}

export function useAreaUnit() {
  return useContext(UnitContext);
}

export function UnitToggle() {
  const { unit, setUnit } = useAreaUnit();
  const t = useTranslation();

  return (
    <div className="flex items-center gap-2">
      <span className="text-xs text-muted-foreground">{t('crop.unitLabel')}</span>
      <div className="inline-flex rounded-md border border-border p-0.5" role="group">
        {(['hectare', 'acre'] as const).map((option) => (
          <button
            key={option}
            type="button"
            onClick={() => setUnit(option)}
            aria-pressed={unit === option}
            className={cn(
              'rounded px-2.5 py-1 text-xs font-medium transition-colors',
              unit === option
                ? 'bg-primary text-primary-foreground'
                : 'text-muted-foreground hover:text-foreground',
            )}
          >
            {t(option === 'hectare' ? 'crop.unitHectare' : 'crop.unitAcre')}
          </button>
        ))}
      </div>
    </div>
  );
}
