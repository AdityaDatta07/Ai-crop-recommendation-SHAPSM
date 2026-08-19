'use client';

import { CalendarCheck, CalendarClock, CalendarX } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useTranslation } from '@/i18n/provider';
import type { CropCalendar } from '@/types/api';

/**
 * Says how far off sowing is, in words.
 *
 * The dates alone were technically correct and practically misleading: asked in
 * August about kharif, the card showed "Sow between 15 Jun 2027" and left the
 * farmer to spot the year.
 */
export function SowingWindowNote({ calendar }: { calendar: CropCalendar }) {
  const t = useTranslation();
  const status = calendar.window_status;
  if (!status) return null;

  const config = {
    open: { icon: CalendarCheck, className: 'bg-emerald-50 text-emerald-900 border-emerald-200' },
    upcoming: { icon: CalendarClock, className: 'bg-muted text-muted-foreground border-border' },
    closed_this_year: { icon: CalendarX, className: 'bg-amber-50 text-amber-900 border-amber-200' },
  }[status];

  const Icon = config.icon;
  const message =
    status === 'open'
      ? t('crop.windowOpen')
      : status === 'upcoming'
        ? t('crop.windowUpcoming', { days: calendar.days_until_sowing ?? 0 })
        : t('crop.windowClosed');

  return (
    <p
      className={cn(
        'mt-3 flex items-center gap-2 rounded-md border px-3 py-2 text-sm',
        config.className,
      )}
    >
      <Icon className="h-4 w-4 shrink-0" aria-hidden />
      {message}
    </p>
  );
}
