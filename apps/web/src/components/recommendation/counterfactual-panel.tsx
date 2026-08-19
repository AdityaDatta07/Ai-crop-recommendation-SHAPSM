'use client';

import { Lightbulb, MoveUp, ShieldAlert, TriangleAlert } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { useI18n } from '@/i18n/provider';
import { useServerText } from '@/i18n/use-server-text';
import type { Attribution, Counterfactual } from '@/types/api';

/**
 * "What would have to change."
 *
 * The reasons panel answers why this crop scored as it did. This answers the
 * question a farmer asks immediately afterwards, and it is the difference
 * between a score and a decision they can act on.
 *
 * Two shapes, rendered differently on purpose:
 *   threshold — a reachable change that moves this crop up
 *   limiting  — nothing reachable helps; here is what is holding it back
 *
 * Flattening those into one style would let "you can fix this" and "you
 * cannot" look identical.
 */
function AttributionBars({ rows }: { rows: Attribution[] }) {
  const { t } = useI18n();
  const serverText = useServerText();
  if (rows.length === 0) return null;

  const total = rows.reduce((sum, row) => sum + row.contribution, 0);
  // Scale bars against the largest factor so small ones stay visible.
  const widest = Math.max(...rows.map((row) => row.contribution + row.headroom), 0.01);

  return (
    <div className="mb-5">
      <h3 className="text-sm font-semibold">{t('counterfactual.attributionTitle')}</h3>
      <p className="mt-0.5 text-xs text-muted-foreground">
        {t('counterfactual.attributionHelp')}
      </p>

      <ul className="mt-3 space-y-2.5">
        {rows.map((row) => (
          <li key={row.factor}>
            <div className="flex items-baseline justify-between gap-3 text-sm">
              <span className="font-medium">{t(`factors.${row.factor}`)}</span>
              <span className="font-mono text-xs text-muted-foreground">
                {row.contribution.toFixed(3)}
              </span>
            </div>

            {/* Filled = earned, hatched = headroom. The gap is the point. */}
            <div className="mt-1 flex h-2 w-full overflow-hidden rounded-full bg-muted">
              <div
                className="h-full bg-primary"
                style={{ width: `${(row.contribution / widest) * 100}%` }}
              />
              <div
                className="h-full bg-amber-200"
                style={{ width: `${(row.headroom / widest) * 100}%` }}
              />
            </div>

            <p className="mt-1 text-xs text-muted-foreground">
              {serverText('reason', row.code, row.params, row.detail)}
            </p>
          </li>
        ))}
      </ul>

      <p className="mt-3 border-t border-border pt-2 text-right text-sm">
        {t('counterfactual.totalScore')}{' '}
        <span className="font-mono font-semibold">{total.toFixed(3)}</span>
      </p>
    </div>
  );
}

/**
 * `kind` selects the sentence, except for irrigation: "at soil pH 6.5 instead
 * of 7.5" does not work for a categorical input, so it gets its own wording.
 */
function counterfactualCode(row: { kind: string; factor: string }): string {
  return row.factor === 'irrigation' && row.kind === 'threshold'
    ? 'irrigation_threshold'
    : row.kind;
}

export function CounterfactualPanel({
  counterfactuals,
  attribution = [],
}: {
  counterfactuals: Counterfactual[];
  attribution?: Attribution[];
}) {
  const { t } = useI18n();
  const serverText = useServerText();
  if (counterfactuals.length === 0 && attribution.length === 0) return null;

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-2 text-base">
          <Lightbulb className="h-4 w-4 text-muted-foreground" aria-hidden />
          {t('counterfactual.title')}
        </CardTitle>
      </CardHeader>

      <CardContent>
        <AttributionBars rows={attribution} />

        <ul className="space-y-3">
          {counterfactuals.map((item) => {
            const actionable = item.kind === 'threshold';
            const fragile = item.kind === 'fragility';
            const Icon = actionable ? MoveUp : fragile ? ShieldAlert : TriangleAlert;

            return (
              <li
                key={`${item.factor}-${item.kind}`}
                className={
                  actionable
                    ? 'rounded-md border border-emerald-200 bg-emerald-50 p-3'
                    : fragile
                      ? 'rounded-md border border-amber-200 bg-amber-50 p-3'
                      : 'rounded-md border border-border bg-muted p-3'
                }
              >
                <div className="flex items-start gap-2">
                  <Icon
                    className={
                      actionable
                        ? 'mt-0.5 h-4 w-4 shrink-0 text-emerald-700'
                        : fragile
                          ? 'mt-0.5 h-4 w-4 shrink-0 text-amber-700'
                          : 'mt-0.5 h-4 w-4 shrink-0 text-muted-foreground'
                    }
                    aria-hidden
                  />
                  <div className="min-w-0 flex-1">
                    <p
                      className={
                        actionable
                          ? 'text-sm text-emerald-900'
                          : fragile
                            ? 'text-sm text-amber-900'
                            : 'text-sm text-muted-foreground'
                      }
                    >
                      {serverText('counterfactual',
                        counterfactualCode(item),
                        item.params,
                        item.message,
                      )}
                    </p>

                    {actionable && item.target_value && (
                      <div className="mt-2 flex flex-wrap items-center gap-2">
                        <Badge variant="outline">{t(`factors.${item.factor}`)}</Badge>
                        <span className="font-mono text-xs text-emerald-900">
                          {item.current_value} → {item.target_value}
                        </span>
                        <Badge variant="positive">
                          {t('counterfactual.rankGain', { places: item.rank_gain })}
                        </Badge>
                      </div>
                    )}
                  </div>
                </div>
              </li>
            );
          })}
        </ul>

        <p className="mt-3 text-xs text-muted-foreground">{t('counterfactual.note')}</p>
      </CardContent>
    </Card>
  );
}
