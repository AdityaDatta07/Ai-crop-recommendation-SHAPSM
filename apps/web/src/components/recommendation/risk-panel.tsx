'use client';

import { ShieldAlert, Sprout } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { formatMoney, formatNumber, NOT_AVAILABLE } from '@/lib/format';
import { useI18n } from '@/i18n/provider';
import { useCropName } from '@/i18n/use-crop-name';
import type { Level, RiskPlan } from '@/types/api';

/**
 * Risk, and whether splitting the field would actually reduce it.
 *
 * The panel is arranged around one claim: a split only helps if the two crops
 * fail for different reasons. So the exposure table comes first — three axes,
 * each traceable to a source — and the plan comes second, as a conclusion drawn
 * from it rather than a recommendation arriving from nowhere.
 *
 * When there is no plan, the reason is the content. "Every crop that suits this
 * field shares the same risk" and "your plot is too small to divide" are useful
 * answers, and rendering them in the same place a plan would have gone is more
 * honest than hiding the panel and leaving the farmer to assume we forgot.
 */

const LEVEL_STYLES: Record<Level, string> = {
  // Not colour alone: the words Low / Medium / High carry the meaning, so this
  // survives a mono printout and a colour-blind reader.
  low: 'border-emerald-300 text-emerald-800',
  medium: 'border-amber-300 text-amber-900',
  high: 'border-red-300 text-red-800',
};

function LevelBadge({ level }: { level: Level }) {
  const { t } = useI18n();
  return (
    <Badge variant="outline" className={LEVEL_STYLES[level]}>
      {t(`risk.level.${level}`)}
    </Badge>
  );
}

export function RiskPanel({ risk }: { risk: RiskPlan | null | undefined }) {
  const { t } = useI18n();

  /** Risk types arrive as identifiers ("pest, weather"); name them in-language. */
  const riskTypes = (list: unknown) =>
    String(list ?? '')
      .split(',')
      .map((kind) => kind.trim())
      .filter(Boolean)
      .map((kind) => t(`risk.type.${kind}`))
      .join(', ');

  const cropName = useCropName();

  if (!risk || risk.exposures.length === 0) return null;

  const plan = risk.plan ?? [];
  const given = risk.margin_given_up;

  return (
    <Card data-print-card>
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-2 text-base">
          <ShieldAlert className="h-4 w-4 text-muted-foreground" aria-hidden />
          {t('risk.title')}
        </CardTitle>
        <p className="text-sm text-muted-foreground">{t('risk.help')}</p>
      </CardHeader>

      <CardContent>
        {/* ------------------------------------------------ exposure table */}
        <h3 className="text-sm font-semibold">{t('risk.exposureTitle')}</h3>

        <div className="mt-2 overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border text-left text-xs text-muted-foreground">
                <th className="py-1.5 pr-3 font-medium">&nbsp;</th>
                <th className="py-1.5 pr-3 font-medium">{t('risk.agronomic')}</th>
                <th className="py-1.5 pr-3 font-medium">{t('risk.price')}</th>
                <th className="py-1.5 font-medium">{t('risk.water')}</th>
              </tr>
            </thead>
            <tbody>
              {risk.exposures.map((exposure) => (
                <tr key={exposure.crop_code} className="border-b border-border/60 last:border-0">
                  <td className="py-2 pr-3">
                    <div className="font-medium">
                      {cropName(exposure.crop_code, exposure.name)}
                    </div>
                    {exposure.severe_risks.length > 0 && (
                      <div className="text-xs text-muted-foreground">
                        {t('risk.severeNote', { risks: exposure.severe_risks.join(', ') })}
                      </div>
                    )}
                  </td>
                  <td className="py-2 pr-3">
                    <LevelBadge level={exposure.agronomic} />
                  </td>
                  <td className="py-2 pr-3">
                    <LevelBadge level={exposure.price} />
                  </td>
                  <td className="py-2">
                    <LevelBadge level={exposure.water} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* ------------------------------------------------------- verdict */}
        <div className="mt-4 rounded-md border border-border bg-muted/40 p-3">
          <p className="text-sm">
            {t(`risk.verdict.${risk.verdict_code}`, {
              // Crop names in the verdict are localised the same way as
              // everywhere else, from the reference data rather than a copy.
              crop: cropName(
                String(risk.verdict_params?.crop_code ?? ''),
                String(risk.verdict_params?.crop ?? ''),
              ),
              partner: cropName(
                String(risk.verdict_params?.partner_code ?? ''),
                String(risk.verdict_params?.partner ?? ''),
              ),
              shared: riskTypes(risk.verdict_params?.shared),
              minimum: String(risk.verdict_params?.minimum ?? ''),
            })}
          </p>
        </div>

        {/* ---------------------------------------------------------- plan */}
        {plan.length > 0 && (
          <div className="mt-4">
            <h3 className="text-sm font-semibold">{t('risk.planTitle')}</h3>

            {/* One bar, split by share. The proportions are the message. */}
            <div className="mt-2 flex h-3 w-full overflow-hidden rounded-full border border-border">
              {plan.map((allocation, index) => (
                <div
                  key={allocation.crop_code}
                  className={index === 0 ? 'bg-primary' : 'bg-emerald-400'}
                  style={{ width: `${allocation.share * 100}%` }}
                />
              ))}
            </div>

            <ul className="mt-3 space-y-2">
              {plan.map((allocation, index) => (
                <li
                  key={allocation.crop_code}
                  className="flex flex-wrap items-baseline justify-between gap-2 text-sm"
                >
                  <span className="flex items-center gap-2">
                    <span
                      className={`inline-block h-2.5 w-2.5 rounded-full ${
                        index === 0 ? 'bg-primary' : 'bg-emerald-400'
                      }`}
                      aria-hidden
                    />
                    <span className="font-medium">
                      {cropName(allocation.crop_code, allocation.name)}
                    </span>
                    <span className="text-xs text-muted-foreground">
                      {Math.round(allocation.share * 100)}% {t('risk.ofField')} ·{' '}
                      {formatNumber(
                        allocation.area_ha,
                        t(allocation.area_ha === 1 ? 'season.areaUnitHaOne' : 'season.areaUnitHa'),
                      )}
                    </span>
                  </span>
                  <span className="font-mono">
                    {allocation.net_margin === null || allocation.net_margin === undefined
                      ? NOT_AVAILABLE
                      : formatMoney(allocation.net_margin)}
                  </span>
                </li>
              ))}
            </ul>

            <div className="mt-3 flex flex-wrap items-baseline justify-between gap-2 border-t border-border pt-2">
              <span className="text-sm font-medium">{t('risk.combined')}</span>
              <span className="font-mono font-semibold">
                {risk.combined_margin === null || risk.combined_margin === undefined
                  ? NOT_AVAILABLE
                  : formatMoney(risk.combined_margin)}
              </span>
            </div>

            {/* The thing the split is being measured against, named. Without
                this row the comparison sentence below asks the reader to take
                "the best single crop" on trust. */}
            {risk.single_crop_margin !== null && risk.single_crop_margin !== undefined && (
              <div className="mt-1 flex flex-wrap items-baseline justify-between gap-2">
                <span className="text-xs text-muted-foreground">
                  {t('risk.bestSingle', {
                    crop: cropName(risk.single_crop_code, risk.single_crop_name),
                  })}
                </span>
                <span className="font-mono text-sm text-muted-foreground">
                  {formatMoney(risk.single_crop_margin)}
                </span>
              </div>
            )}

            {/* The price of the protection, stated plainly. It can be
                negative — a split occasionally earns more, when the partner
                pays better per hectare than the crop that fits best — and that
                deserves its own sentence rather than a minus sign. */}
            {given !== null && given !== undefined && (
              <p className="mt-2 text-xs text-muted-foreground">
                {Math.abs(given) < 1
                  ? t('risk.aboutLevel')
                  : given > 0
                    ? t('risk.costsYou', {
                        amount: formatMoney(given),
                        crop: cropName(risk.single_crop_code, risk.single_crop_name),
                      })
                    : t('risk.earnsMore', { amount: formatMoney(Math.abs(given)) })}
              </p>
            )}

            {risk.overlap !== null && risk.overlap !== undefined && risk.overlap < 0.3 && (
              <p className="mt-2 flex items-start gap-1.5 text-xs text-muted-foreground">
                <Sprout className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />
                {t('risk.overlapLow')}
              </p>
            )}
          </div>
        )}

        <p className="mt-4 border-t border-border pt-2 text-xs text-muted-foreground">
          {t('risk.rule')}
        </p>
      </CardContent>
    </Card>
  );
}
