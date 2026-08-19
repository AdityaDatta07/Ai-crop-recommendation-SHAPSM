'use client';

import Link from 'next/link';
import { Repeat, ArrowRight } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { useI18n } from '@/i18n/provider';
import { useServerText } from '@/i18n/use-server-text';
import { useCropName } from '@/i18n/use-crop-name';
import type { Recommendation } from '@/types/api';

/**
 * What last season's crop does to this season's shortlist.
 *
 * WHY THIS IS A PANEL RATHER THAN JUST A REASON
 * ---------------------------------------------
 * Rotation is scored per crop and already flows into `reasons`. But reasons
 * show the four strongest factors, so rotation only appeared when it happened
 * to outrank pH or temperature — which meant the farmer answered a question
 * and frequently saw no trace of it anywhere. A feature you cannot find is a
 * feature you did not ship.
 *
 * Here every candidate is listed against the same predecessor, so the effect
 * is visible as a comparison rather than buried as a footnote on one card.
 *
 * WHEN NOTHING WAS ENTERED
 * ------------------------
 * The panel still renders, and says what answering would buy. Silence would
 * leave the farmer with no way to discover that the question matters.
 */

/** Bands for the rotation score. The words carry the meaning, not the colour. */
function band(score: number): { key: string; className: string } {
  if (score >= 0.85) return { key: 'good', className: 'border-emerald-300 text-emerald-800' };
  if (score >= 0.6) return { key: 'fine', className: 'border-border text-muted-foreground' };
  if (score >= 0.4) return { key: 'poor', className: 'border-amber-300 text-amber-900' };
  return { key: 'bad', className: 'border-red-300 text-red-800' };
}

export function RotationPanel({
  recommendations,
  previousCrop,
}: {
  recommendations: Recommendation[];
  previousCrop?: string | null;
}) {
  const { t } = useI18n();
  const serverText = useServerText();
  const cropName = useCropName();

  const scored = recommendations.filter((item) => item.rotation);

  if (!previousCrop || scored.length === 0) {
    return (
      <Card data-print-card>
        <CardHeader className="pb-2">
          <CardTitle className="flex items-center gap-2 text-base">
            <Repeat className="h-4 w-4 text-muted-foreground" aria-hidden />
            {t('rotation.title')}
          </CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">{t('rotation.notAsked')}</p>
          <Link
            href="/"
            className="no-print mt-3 inline-flex items-center gap-1.5 text-sm text-primary hover:underline"
          >
            {t('rotation.goAnswer')}
            <ArrowRight className="h-3.5 w-3.5" aria-hidden />
          </Link>
        </CardContent>
      </Card>
    );
  }

  const previousName = cropName(previousCrop, previousCrop);

  return (
    <Card data-print-card>
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-2 text-base">
          <Repeat className="h-4 w-4 text-muted-foreground" aria-hidden />
          {t('rotation.title')}
        </CardTitle>
        <p className="text-sm text-muted-foreground">
          {t('rotation.help', { previous: previousName })}
        </p>
      </CardHeader>

      <CardContent>
        <ul className="space-y-2.5">
          {scored.map((item) => {
            const rotation = item.rotation!;
            const { key, className } = band(rotation.score);

            return (
              <li key={item.crop_code} className="border-b border-border/60 pb-2.5 last:border-0">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-medium">{cropName(item.crop_code, item.name)}</span>
                  <Badge variant="outline" className={className}>
                    {t(`rotation.band.${key}`)}
                  </Badge>
                </div>
                <p className="mt-0.5 text-sm text-muted-foreground">
                  {serverText('reason', rotation.code, rotation.params, '')}
                </p>
              </li>
            );
          })}
        </ul>

        <p className="mt-3 text-xs text-muted-foreground">{t('rotation.note')}</p>
      </CardContent>
    </Card>
  );
}
