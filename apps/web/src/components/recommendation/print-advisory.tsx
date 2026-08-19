'use client';

import { Printer } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useI18n } from '@/i18n/provider';
import { useCropName } from '@/i18n/use-crop-name';
import { useServerText } from '@/i18n/use-server-text';
import { formatDate, formatMoney, formatNumber, NOT_AVAILABLE } from '@/lib/format';
import type { RecommendationResponse } from '@/types/api';

/**
 * Printable advisory.
 *
 * Deliberately the browser's own print-to-PDF rather than a generated file.
 * Devanagari embedding in a server-side PDF library is fiddly and easy to get
 * subtly wrong — a farmer would get boxes instead of Hindi. The browser already
 * has the fonts and already renders this page correctly, so printing it is both
 * simpler and more reliable. It also works with no network.
 */
export function PrintAdvisoryButton() {
  const { t } = useI18n();
  const serverText = useServerText();

  return (
    <Button
      type="button"
      variant="outline"
      size="sm"
      onClick={() => window.print()}
      className="no-print"
    >
      <Printer className="h-4 w-4" aria-hidden />
      {t('print.download')}
    </Button>
  );
}

/**
 * The identifying header, printed but never shown on screen.
 *
 * request_id is on here on purpose: it is what lets a bank or KVK officer look
 * the advisory up, and what makes the sheet traceable back to the exact inputs
 * that produced it.
 */
export function PrintHeader({ data }: { data: RecommendationResponse }) {
  const { t } = useI18n();
  const serverText = useServerText();
  const place = data.location_resolved;

  return (
    <div className="print-header">
      <h1 className="text-lg font-semibold">{t('print.title')}</h1>
      <p className="text-sm">
        {place.district_name}, {place.state_code} · {formatNumber(place.area_ha, 'ha')}
        {place.area_acres ? ` (${formatNumber(place.area_acres)} acres)` : ''}
      </p>
      <p className="text-xs">
        {t('print.reference', { id: data.request_id })} ·{' '}
        {t('print.generated', { date: formatDate(data.generated_at.slice(0, 10)) })}
      </p>
    </div>
  );
}

/**
 * Full detail for every ranked crop, laid out for paper.
 *
 * On screen the ranked list is a set of tappable cards leading to detail pages.
 * On paper there is nowhere to tap, so everything the farmer would have drilled
 * into has to be present at once.
 */
export function PrintCropDetail({ data }: { data: RecommendationResponse }) {
  const cropName = useCropName();
  const { t } = useI18n();
  const serverText = useServerText();

  return (
    <div className="print-only">
      {data.recommendations.map((crop) => (
        <div key={crop.crop_code} data-print-crop className="mb-4 border-b pb-3">
          <h3 className="font-semibold">
            {crop.rank}. {cropName(crop.crop_code, crop.name)}
            {crop.variety_suggested ? ` — ${crop.variety_suggested}` : ''}
          </h3>

          <p className="text-xs">
            {t('crop.confidence', { level: t(`crop.${crop.confidence}`) })} ·{' '}
            {t('crop.suitability', { score: Math.round(crop.score * 100) })}
          </p>

          <ul className="mt-1 text-xs">
            {crop.reasons.map((reason) => (
              <li key={`${reason.factor}-${reason.detail}`}>
                <strong>{t(`factors.${reason.factor}`)}:</strong>{' '}
                {serverText('reason', reason.code, reason.params, reason.detail)}
              </li>
            ))}
          </ul>

          <table className="mt-2 w-full text-xs">
            <tbody>
              <tr>
                <td>{t('crop.sowBetween')}</td>
                <td className="text-right">
                  {formatDate(crop.calendar.sowing_window.start)} –{' '}
                  {formatDate(crop.calendar.sowing_window.end)}
                </td>
              </tr>
              <tr>
                <td>{t('crop.harvestAround')}</td>
                <td className="text-right">
                  {formatDate(crop.calendar.harvest_window.start)} –{' '}
                  {formatDate(crop.calendar.harvest_window.end)}
                </td>
              </tr>
              <tr>
                <td>{t('crop.expectedYield')}</td>
                <td className="text-right">
                  {formatNumber(crop.economics.expected_yield_t_ha, 't/ha')}
                </td>
              </tr>
              <tr>
                <td>{t('crop.inputCost')}</td>
                <td className="text-right">
                  {crop.economics.input_cost_per_ha === null
                    ? NOT_AVAILABLE
                    : `${formatMoney(crop.economics.input_cost_per_ha)}/ha`}
                </td>
              </tr>
              <tr>
                <td>
                  <strong>{t('crop.netMargin')}</strong>
                </td>
                <td className="text-right">
                  <strong>{formatMoney(crop.economics.net_margin)}</strong>
                </td>
              </tr>
            </tbody>
          </table>

          {/* Provenance travels with the figure. That is the whole point of a
              printed advisory: the reader can check it. */}
          {crop.economics.price_source && (
            <p className="mt-1 text-[9px]">
              {t('crop.priceSource', { source: crop.economics.price_source })}
            </p>
          )}

          {crop.risks.length > 0 && (
            <p className="mt-1 text-xs">
              <strong>{t('crop.risks')}:</strong>{' '}
              {crop.risks.map((risk) => `${risk.name} (${risk.severity})`).join(', ')}
            </p>
          )}
        </div>
      ))}
    </div>
  );
}

export function PrintFooter() {
  const { t } = useI18n();
  const serverText = useServerText();
  return (
    <div className="print-footer">
      <p>{t('app.disclaimer')}</p>
    </div>
  );
}
