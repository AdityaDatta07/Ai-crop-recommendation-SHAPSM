'use client';

import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { Bookmark, BookmarkCheck, Trash2, Download, HardDrive, CalendarPlus } from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { useI18n } from '@/i18n/provider';
import { useCropName } from '@/i18n/use-crop-name';
import { formatNumber, formatTimestamp } from '@/lib/format';
import {
  exportAll,
  isPlanSaved,
  loadPlans,
  removePlan,
  savePlan,
  storageAvailable,
  type SavedPlan,
} from '@/lib/local-store';
import { buildIcs, downloadIcs, reminderEvents } from '@/lib/reminders';
import type { RecommendationResponse } from '@/types/api';

/**
 * Saving a plan, and getting reminded about it.
 *
 * WHAT "SAVED" HONESTLY MEANS HERE
 * --------------------------------
 * This device, this browser. No account, no server copy. Clearing browser data
 * or moving to another phone loses everything, so the panel says so rather
 * than letting the word carry a promise it cannot keep. That sentence is not
 * an apology for a limitation — it is the difference between a farmer who
 * knows to export a copy and one who finds out the hard way.
 *
 * WHY THE ADVISORY IS NOT COPIED IN
 * ---------------------------------
 * Only the request id and a few labels are stored. Opening a saved plan
 * refetches it, so prices and satellite readings are current. A stored copy
 * would render last month's numbers in a layout identical to today's, with
 * nothing on screen to tell them apart.
 */

// ---------------------------------------------------------- save + remind

export function SavePlanButton({ data }: { data: RecommendationResponse }) {
  const { t, locale } = useI18n();
  const cropName = useCropName();
  const [saved, setSaved] = useState(false);
  const [available, setAvailable] = useState(true);

  // localStorage is not readable during render on the server, so the first
  // paint must not depend on it.
  useEffect(() => {
    setAvailable(storageAvailable());
    setSaved(isPlanSaved(data.request_id));
  }, [data.request_id]);

  if (!available) return null;

  function toggle() {
    if (saved) {
      removePlan(data.request_id);
      setSaved(false);
      return;
    }
    const top = data.recommendations[0];
    const ok = savePlan({
      requestId: data.request_id,
      // Defaults to the district. Renaming happens in the list, where there is
      // room for a keyboard and no risk of interrupting the read.
      label: data.location_resolved.district_name,
      districtName: data.location_resolved.district_name,
      season: data.request_echo?.season ?? '',
      areaHa: data.location_resolved.area_ha,
      topCrop: top?.name ?? '',
      topCropCode: top?.crop_code ?? '',
      savedAt: new Date().toISOString(),
    });
    // Only claim it saved if the write actually succeeded. Quota errors are
    // silent otherwise, and "Saved" on a button that saved nothing is the one
    // failure worse than not saving.
    setSaved(ok);
  }

  function addReminders() {
    const events = reminderEvents(
      data,
      {
        sow: (crop) => t('reminders.sowSummary', { crop }),
        harvest: (crop) => t('reminders.harvestSummary', { crop }),
        description: (crop, district) => t('reminders.description', { crop, district }),
      },
      cropName,
    );
    if (events.length === 0) return;
    downloadIcs(`beej-nirnay-${data.request_id}.ics`, buildIcs(events));
  }

  return (
    <>
      <Button type="button" variant="outline" onClick={toggle} className="no-print">
        {saved ? (
          <BookmarkCheck className="h-4 w-4 text-emerald-700" aria-hidden />
        ) : (
          <Bookmark className="h-4 w-4" aria-hidden />
        )}
        {saved ? t('saved.savedLabel') : t('saved.saveLabel')}
      </Button>

      <Button type="button" variant="outline" onClick={addReminders} className="no-print">
        <CalendarPlus className="h-4 w-4" aria-hidden />
        {t('reminders.add')}
      </Button>
      <span className="sr-only">{locale}</span>
    </>
  );
}

// ------------------------------------------------------------------ list

export function SavedPlansPanel() {
  const { t } = useI18n();
  const cropName = useCropName();
  const [plans, setPlans] = useState<SavedPlan[]>([]);
  const [available, setAvailable] = useState(true);

  const refresh = useCallback(() => setPlans(loadPlans()), []);

  useEffect(() => {
    setAvailable(storageAvailable());
    refresh();
  }, [refresh]);

  function rename(plan: SavedPlan, label: string) {
    savePlan({ ...plan, label: label.trim() || plan.districtName });
    refresh();
  }

  function exportFile() {
    const blob = new Blob([exportAll()], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = 'beej-nirnay-backup.json';
    anchor.click();
    URL.revokeObjectURL(url);
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Bookmark className="h-5 w-5 text-emerald-700" aria-hidden />
          {t('saved.heading')}
        </CardTitle>
        <CardDescription>{t('saved.what')}</CardDescription>
      </CardHeader>

      <CardContent className="space-y-4">
        {/* Not a footnote. A farmer who logs three seasons and then clears
            their browser would be right to be angry, and this is the only
            warning they get. */}
        <p className="flex items-start gap-2 rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
          <HardDrive className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
          {t('saved.deviceOnly')}
        </p>

        {!available && <p className="text-sm text-muted-foreground">{t('saved.unavailable')}</p>}

        {available && plans.length === 0 && (
          <p className="text-sm text-muted-foreground">{t('saved.empty')}</p>
        )}

        {plans.map((plan) => (
          <div key={plan.requestId} className="rounded-lg border border-border p-3">
            <div className="flex flex-wrap items-start justify-between gap-2">
              <input
                defaultValue={plan.label}
                aria-label={t('saved.nameLabel')}
                onBlur={(event) => rename(plan, event.target.value)}
                className="min-w-0 flex-1 rounded border border-transparent bg-transparent px-1 py-0.5 font-medium hover:border-border focus:border-emerald-500 focus:outline-none"
              />
              <button
                type="button"
                onClick={() => {
                  removePlan(plan.requestId);
                  refresh();
                }}
                aria-label={t('saved.remove')}
                className="text-muted-foreground transition-colors hover:text-destructive"
              >
                <Trash2 className="h-4 w-4" aria-hidden />
              </button>
            </div>

            <p className="mt-1 text-sm text-muted-foreground">
              {t('saved.summary', {
                district: plan.districtName,
                season: t(`season.${plan.season}`),
                area: formatNumber(plan.areaHa, 'ha'),
                crop: cropName(plan.topCropCode, plan.topCrop),
              })}
            </p>
            <p className="text-xs text-muted-foreground">
              {t('saved.savedOn', { date: formatTimestamp(plan.savedAt) })}
            </p>

            <Link
              href={`/r/${plan.requestId}`}
              className="mt-2 inline-block text-sm font-medium text-emerald-800 hover:underline"
            >
              {t('saved.open')}
            </Link>
          </div>
        ))}

        {plans.length > 0 && (
          <Button type="button" variant="outline" onClick={exportFile}>
            <Download className="h-4 w-4" aria-hidden />
            {t('saved.export')}
          </Button>
        )}
      </CardContent>
    </Card>
  );
}
