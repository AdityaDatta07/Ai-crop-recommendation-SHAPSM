'use client';

import { useState } from 'react';
import { ChevronDown, FlaskConical } from 'lucide-react';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Card } from '@/components/ui/card';
import { cn } from '@/lib/utils';
import { useTranslation } from '@/i18n/provider';
import type { SoilTest } from '@/types/api';

const NUTRIENTS = [
  { key: 'nitrogen_kg_ha', label: 'soil.nitrogen', symbol: 'N', max: 2000 },
  { key: 'phosphorus_kg_ha', label: 'soil.phosphorus', symbol: 'P', max: 500 },
  { key: 'potassium_kg_ha', label: 'soil.potassium', symbol: 'K', max: 2000 },
] as const;

/**
 * Optional Soil Health Card entry.
 *
 * This exists because no satellite can measure plant-available N, P or K — it
 * is a laboratory result. Nearly every Indian farmer has these three numbers
 * printed on a card, so asking is both the most accurate route and the only
 * honest one.
 *
 * Collapsed by default: a farmer without their card should not face three empty
 * boxes implying the tool needs something they cannot give.
 */
export function SoilTestFields({
  value,
  onChange,
}: {
  value: SoilTest;
  onChange: (next: SoilTest) => void;
}) {
  const t = useTranslation();
  const [open, setOpen] = useState(false);
  const [errors, setErrors] = useState<Record<string, string | null>>({});

  const filled = NUTRIENTS.filter(
    (n) => value[n.key] !== null && value[n.key] !== undefined,
  ).length;

  function update(key: keyof SoilTest, raw: string, max: number) {
    if (raw.trim() === '') {
      setErrors((prev) => ({ ...prev, [key]: null }));
      onChange({ ...value, [key]: null });
      return;
    }

    const parsed = Number.parseFloat(raw);
    if (!Number.isFinite(parsed) || parsed < 0) {
      setErrors((prev) => ({ ...prev, [key]: t('soil.invalid') }));
      return;
    }
    if (parsed > max) {
      // Almost always a decimal slip rather than a real reading.
      setErrors((prev) => ({ ...prev, [key]: t('soil.tooHigh', { max }) }));
      return;
    }

    setErrors((prev) => ({ ...prev, [key]: null }));
    onChange({ ...value, [key]: parsed });
  }

  return (
    // A Card, not a bare bordered div.
    //
    // Every other section on this form is a Card, which carries `bg-card`.
    // This one was the exception, so after the theme inverted it had no
    // background at all: dark labels sitting directly on the dark canvas,
    // legible only where the decorative layer happened to be light. The bug
    // was invisible in the old light theme because the page behind it was
    // white anyway.
    <Card className="overflow-hidden">
      <button
        type="button"
        onClick={() => setOpen((prev) => !prev)}
        aria-expanded={open}
        className="flex w-full items-center justify-between gap-3 p-4 text-left"
      >
        <span className="flex items-center gap-2">
          <FlaskConical className="h-4 w-4 text-muted-foreground" aria-hidden />
          <span className="text-sm font-medium">{t('soil.heading')}</span>
          {filled > 0 && (
            <span className="rounded-full bg-primary/10 px-2 py-0.5 text-xs text-primary">
              {t('soil.filled', { count: filled })}
            </span>
          )}
        </span>
        <ChevronDown
          className={cn('h-4 w-4 text-muted-foreground transition-transform', open && 'rotate-180')}
          aria-hidden
        />
      </button>

      {open && (
        <div className="border-t border-border p-4">
          <p className="mb-3 text-sm text-muted-foreground">{t('soil.help')}</p>

          <div className="grid gap-4 sm:grid-cols-3">
            {NUTRIENTS.map((nutrient) => (
              <div key={nutrient.key} className="space-y-1.5">
                <Label htmlFor={nutrient.key}>
                  {t(nutrient.label)}{' '}
                  <span className="text-muted-foreground">({nutrient.symbol}, kg/ha)</span>
                </Label>
                <Input
                  id={nutrient.key}
                  inputMode="decimal"
                  placeholder="—"
                  defaultValue={value[nutrient.key] ?? ''}
                  aria-invalid={Boolean(errors[nutrient.key])}
                  onChange={(event) =>
                    update(nutrient.key, event.target.value, nutrient.max)
                  }
                />
                {errors[nutrient.key] && (
                  <p className="text-sm text-destructive">{errors[nutrient.key]}</p>
                )}
              </div>
            ))}
          </div>

          <p className="mt-3 text-xs text-muted-foreground">{t('soil.partialOk')}</p>
        </div>
      )}
    </Card>
  );
}
