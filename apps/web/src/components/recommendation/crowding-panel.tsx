'use client';

import { Users, LineChart, Info } from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { useI18n } from '@/i18n/provider';
import { useCropName } from '@/i18n/use-crop-name';
import { useServerText } from '@/i18n/use-server-text';
import type { Crowding } from '@/types/api';

/**
 * How crowded a crop choice is, from the only two angles we can honestly see.
 *
 * WHAT THIS PANEL IS NOT
 * ----------------------
 * It is not "62% of Nashik plots are going to onion". Nobody publishes district
 * sowing intentions in time to act on them, and inventing that figure would
 * have been the one fabricated number in an app whose whole argument is that
 * its numbers are traceable.
 *
 * WHAT IT IS
 * ----------
 * Left: how often THIS TOOL ranked each crop first in this district and season.
 * A count of our own advice. That is a modest claim and it is a true one, and
 * it carries a real warning: an advisory followed at scale becomes a cause of
 * the glut it is warning about.
 *
 * Right: what the crop actually fetched in its harvest month in previous years,
 * from recorded mandi prices. Backward-looking, and labelled as such.
 *
 * THE CAVEAT IS NOT A FOOTNOTE
 * ----------------------------
 * `advisories_not_farmers` renders above the numbers, not below them. The
 * misreading it prevents — advisories taken for farmers — happens at the moment
 * the percentage is seen, so an explanation underneath arrives too late. This
 * is the same reason the sowing-window warning sits above the tabs rather than
 * inside one.
 */

const BAND_VARIANT = {
  crowded: 'negative',
  common: 'secondary',
  uncommon: 'outline',
  never: 'outline',
  unknown: 'outline',
} as const;

const DIP_VARIANT = {
  steep: 'negative',
  mild: 'secondary',
  none: 'outline',
  unknown: 'outline',
} as const;

export function CrowdingPanel({ crowding }: { crowding: Crowding[] | undefined }) {
  const { t } = useI18n();
  const cropName = useCropName();
  const serverText = useServerText();

  if (!crowding || crowding.length === 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>{t('crowding.heading')}</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">{t('crowding.empty')}</p>
        </CardContent>
      </Card>
    );
  }

  // Collected across crops rather than repeated per row: the same three
  // sentences under every crop is how a caveat teaches people to skip caveats.
  const caveats = [...new Set(crowding.flatMap((item) => item.caveat_codes))];

  // Every crop in one response shares the same district totals, so the seeded
  // count is a property of the panel rather than of a row.
  const seededCount = crowding[0]?.seeded_advisories ?? 0;

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t('crowding.heading')}</CardTitle>
        <CardDescription>{t('crowding.intro')}</CardDescription>
      </CardHeader>

      <CardContent className="space-y-4">
        {caveats.map((code) => (
          <p
            key={code}
            className="flex items-start gap-2 rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900"
          >
            <Info className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
            <span>{serverText('crowding', code, { seeded: seededCount }, '')}</span>
          </p>
        ))}

        <div className="space-y-4">
          {crowding.map((item) => (
            <div key={item.crop_code} className="rounded-lg border border-border p-4">
              <h3 className="font-medium">{cropName(item.crop_code, item.name)}</h3>

              <div className="mt-3 grid gap-4 sm:grid-cols-2">
                <section className="space-y-1.5">
                  <p className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                    <Users className="h-3.5 w-3.5" aria-hidden />
                    {t('crowding.adviceHeading')}
                  </p>
                  <Badge variant={BAND_VARIANT[item.concentration.band]}>
                    {t(`crowding.band_${item.concentration.band}`)}
                  </Badge>
                  <p className="text-sm text-muted-foreground">
                    {serverText(
                      'crowding',
                      item.concentration.code,
                      item.concentration.params,
                      '',
                    )}
                  </p>
                </section>

                <section className="space-y-1.5">
                  <p className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                    <LineChart className="h-3.5 w-3.5" aria-hidden />
                    {t('crowding.dipHeading')}
                  </p>
                  <div className="flex flex-wrap items-center gap-1.5">
                    <Badge variant={DIP_VARIANT[item.dip.band]}>
                      {t(`crowding.dipband_${item.dip.band}`)}
                    </Badge>
                    {/* Which market these prices are from. Absent when there
                        is no figure, so the label never appears beside a
                        blank. */}
                    {item.dip.scope !== 'none' && (
                      <span className="text-xs text-muted-foreground">
                        {t(
                          item.dip.scope === 'district'
                            ? 'crowding.scopeDistrict'
                            : 'crowding.scopeNational',
                        )}
                      </span>
                    )}
                  </div>
                  <p className="text-sm text-muted-foreground">
                    {serverText('crowding', item.dip.code, item.dip.params, '')}
                  </p>
                </section>
              </div>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}
