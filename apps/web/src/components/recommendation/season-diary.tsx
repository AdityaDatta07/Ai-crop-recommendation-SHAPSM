'use client';

import { useCallback, useEffect, useState } from 'react';
import { NotebookPen, Trash2, Plus } from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { useI18n } from '@/i18n/provider';
import {
  loadDiary,
  removeDiaryEntry,
  saveDiaryEntry,
  storageAvailable,
  type DiaryEntry,
} from '@/lib/local-store';
import type { RecommendationResponse } from '@/types/api';

/**
 * What was actually sown, and what actually came of it.
 *
 * WHY THIS IS THE MOST VALUABLE THING ON THE PAGE
 * -----------------------------------------------
 * Every yield figure in this app is a historical district average, and the
 * handover has said since week one that the weakest claim in the project is
 * that the scoring weights have never been validated against real outcomes.
 *
 * This is where real outcomes would come from. Two seasons of a farmer
 * recording what they sowed, what they harvested and what they sold it for is
 * worth more than any additional satellite index, because it is the only data
 * here that can tell us we were wrong.
 *
 * IT RECORDS WHAT THEY DID, NOT WHAT WE SAID
 * ------------------------------------------
 * The crop field is free text and defaults to nothing. A farmer who ignored
 * the recommendation and sowed something else is the most informative case in
 * the dataset, and pre-filling our own suggestion would quietly discourage
 * them from recording it.
 *
 * NOTHING HERE FEEDS THE RANKER
 * -----------------------------
 * Not yet, and not without an agronomist looking at it first. One farmer's
 * yield on one plot is an anecdote; treating it as a correction would make the
 * model worse in a way nobody could see.
 */
export function SeasonDiary({ data }: { data: RecommendationResponse }) {
  const { t } = useI18n();
  const [entries, setEntries] = useState<DiaryEntry[]>([]);
  const [available, setAvailable] = useState(true);
  const [adding, setAdding] = useState(false);

  const refresh = useCallback(() => setEntries(loadDiary(data.request_id)), [data.request_id]);

  useEffect(() => {
    setAvailable(storageAvailable());
    refresh();
  }, [refresh]);

  function add(form: HTMLFormElement) {
    const fields = new FormData(form);
    const crop = String(fields.get('cropSown') ?? '').trim();
    if (!crop) return;

    const toNumber = (name: string) => {
      const raw = String(fields.get(name) ?? '').trim();
      if (!raw) return null;
      const value = Number.parseFloat(raw);
      // A blank and a zero are different answers. Nulls stay null rather than
      // collapsing to 0, which would read later as "harvested nothing".
      return Number.isFinite(value) && value >= 0 ? value : null;
    };

    saveDiaryEntry({
      id: `${data.request_id}-${Date.now()}`,
      requestId: data.request_id,
      cropSown: crop,
      sownOn: String(fields.get('sownOn') ?? ''),
      harvestedOn: String(fields.get('harvestedOn') ?? '') || undefined,
      yieldQuintal: toNumber('yieldQuintal'),
      soldPricePerQuintal: toNumber('soldPricePerQuintal'),
      notes: String(fields.get('notes') ?? '').trim() || undefined,
      updatedAt: new Date().toISOString(),
    });
    form.reset();
    setAdding(false);
    refresh();
  }

  if (!available) return null;

  return (
    <Card className="no-print">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <NotebookPen className="h-5 w-5 text-emerald-700" aria-hidden />
          {t('diary.heading')}
        </CardTitle>
        <CardDescription>{t('diary.what')}</CardDescription>
      </CardHeader>

      <CardContent className="space-y-4">
        <p className="text-sm text-muted-foreground">{t('diary.why')}</p>

        {entries.map((entry) => (
          <div key={entry.id} className="rounded-lg border border-border p-3">
            <div className="flex items-start justify-between gap-2">
              <div>
                <p className="font-medium">{entry.cropSown}</p>
                <p className="text-sm text-muted-foreground">
                  {t('diary.sownOn', { date: entry.sownOn || '—' })}
                  {entry.harvestedOn && ` · ${t('diary.harvestedOn', { date: entry.harvestedOn })}`}
                </p>
                {(typeof entry.yieldQuintal === 'number' ||
              typeof entry.soldPricePerQuintal === 'number') && (
                  <p className="text-sm text-muted-foreground">
                    {typeof entry.yieldQuintal === 'number' &&
                      t('diary.yieldValue', { value: entry.yieldQuintal })}
                    {typeof entry.yieldQuintal === 'number' &&
                      typeof entry.soldPricePerQuintal === 'number' &&
                      ' · '}
                    {typeof entry.soldPricePerQuintal === 'number' &&
                      t('diary.priceValue', { value: entry.soldPricePerQuintal })}
                  </p>
                )}
                {entry.notes && <p className="mt-1 text-sm">{entry.notes}</p>}
              </div>
              <button
                type="button"
                onClick={() => {
                  removeDiaryEntry(entry.id);
                  refresh();
                }}
                aria-label={t('diary.remove')}
                className="text-muted-foreground transition-colors hover:text-destructive"
              >
                <Trash2 className="h-4 w-4" aria-hidden />
              </button>
            </div>
          </div>
        ))}

        {adding ? (
          <form
            onSubmit={(event) => {
              event.preventDefault();
              add(event.currentTarget);
            }}
            className="space-y-3 rounded-lg border border-border p-3"
          >
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="space-y-1.5">
                <Label htmlFor="cropSown">{t('diary.cropSown')}</Label>
                {/* Free text and empty by default. A farmer who ignored the
                    recommendation is the most informative entry in the set. */}
                <Input id="cropSown" name="cropSown" required placeholder={t('diary.cropHint')} />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="sownOn">{t('diary.sownDate')}</Label>
                <Input id="sownOn" name="sownOn" type="date" />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="harvestedOn">{t('diary.harvestDate')}</Label>
                <Input id="harvestedOn" name="harvestedOn" type="date" />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="yieldQuintal">{t('diary.yieldLabel')}</Label>
                <Input id="yieldQuintal" name="yieldQuintal" inputMode="decimal" placeholder="—" />
              </div>
              <div className="space-y-1.5 sm:col-span-2">
                <Label htmlFor="soldPricePerQuintal">{t('diary.priceLabel')}</Label>
                <Input
                  id="soldPricePerQuintal"
                  name="soldPricePerQuintal"
                  inputMode="decimal"
                  placeholder="—"
                />
              </div>
              <div className="space-y-1.5 sm:col-span-2">
                <Label htmlFor="notes">{t('diary.notesLabel')}</Label>
                <Input id="notes" name="notes" placeholder={t('diary.notesHint')} />
              </div>
            </div>

            <p className="text-xs text-muted-foreground">{t('diary.laterOk')}</p>

            <div className="flex gap-2">
              <Button type="submit">{t('diary.save')}</Button>
              <Button type="button" variant="outline" onClick={() => setAdding(false)}>
                {t('actions.cancel')}
              </Button>
            </div>
          </form>
        ) : (
          <Button type="button" variant="outline" onClick={() => setAdding(true)}>
            <Plus className="h-4 w-4" aria-hidden />
            {t('diary.add')}
          </Button>
        )}

        <p className="text-xs text-muted-foreground">{t('diary.deviceOnly')}</p>
      </CardContent>
    </Card>
  );
}
