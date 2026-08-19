'use client';

import { use } from 'react';
import Link from 'next/link';
import { ArrowLeft, Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { CropCard } from '@/components/recommendation/crop-card';
import { ConditionsPanel } from '@/components/recommendation/conditions-panel';
import { WarningsList } from '@/components/recommendation/warnings-list';
import { ComparisonCard } from '@/components/recommendation/comparison-card';
import { ImpactCalculator } from '@/components/recommendation/impact-calculator';
import { RiskPanel } from '@/components/recommendation/risk-panel';
import { RotationPanel } from '@/components/recommendation/rotation-panel';
import { PrecisionNotice } from '@/components/recommendation/precision-notice';
import { TwoOrderings } from '@/components/recommendation/two-orderings';
import { ListenButton } from '@/components/recommendation/listen-button';
import { CrowdingPanel } from '@/components/recommendation/crowding-panel';
import { ChatBox } from '@/components/recommendation/chat-box';
import {
  MspPanel,
  PslPanel,
  SchemesPanel,
  EmandiPanel,
  InputsPanel,
  RentalPanel,
  BuyersPanel,
  CreditApplySection,
} from '@/components/recommendation/reference-panels';
import { SavePlanButton, SavedPlansPanel } from '@/components/recommendation/saved-plans';
import { SeasonDiary } from '@/components/recommendation/season-diary';
import { ResultTabs, type ResultTab } from '@/components/recommendation/result-tabs';
import {
  LayoutDashboard,
  Droplets,
  ShieldAlert,
  Users,
  IndianRupee,
  Landmark,
  FileText,
  Store,
  Bookmark,
  ShoppingCart,
  Tractor,
  Handshake,
} from 'lucide-react';
import { WaterPanel } from '@/components/recommendation/water-panel';
import {
  PrintAdvisoryButton,
  PrintCropDetail,
  PrintFooter,
  PrintHeader,
} from '@/components/recommendation/print-advisory';
import { useRecommendationById } from '@/lib/queries';
import { userMessage } from '@/lib/api-error';
import { formatNumber, formatTimestamp } from '@/lib/format';
import { useTranslation } from '@/i18n/provider';

export default function ResultsPage({ params }: { params: Promise<{ request_id: string }> }) {
  const t = useTranslation();
  const { request_id: requestId } = use(params);
  const { data, isLoading, isError, error } = useRecommendationById(requestId);

  if (isLoading) {
    return (
      <div className="mx-auto max-w-3xl space-y-4">
        <p className="on-canvas-muted flex items-center gap-2 text-sm">
          <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
          {t('results.loading')}
        </p>
        {[0, 1, 2].map((i) => (
          <Skeleton key={i} className="h-44 w-full" />
        ))}
      </div>
    );
  }

  if (isError || !data) {
    return (
      <div className="mx-auto max-w-3xl space-y-4">
        <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive">
          {userMessage(error)}
        </div>
        <Link href="/">
          <Button variant="outline">{t('actions.startAgain')}</Button>
        </Link>
      </div>
    );
  }

  const { location_resolved: place, recommendations } = data;

  const sections: ResultTab[] = [
    {
      id: 'dashboard',
      label: t('tabs.dashboard'),
      icon: LayoutDashboard,
      content: (
        <>
          {data.comparison && <ComparisonCard comparison={data.comparison} />}
          <RotationPanel
            recommendations={recommendations}
            previousCrop={data.request_echo?.previous_crop}
          />
          <ConditionsPanel conditions={data.conditions} location={place} />
          <TwoOrderings recommendations={recommendations} />
          {recommendations.length === 0 ? (
            <p className="on-canvas-muted rounded-xl border border-white/15 bg-white/5 p-6 text-center">
              {t('results.empty')}
            </p>
          ) : (
            <div className="space-y-3 no-print">
              <h2 className="on-canvas-muted text-sm font-semibold uppercase tracking-wide">
                {t('results.ranked')}
              </h2>
              {recommendations.map((recommendation) => (
                <CropCard
                  key={recommendation.crop_code}
                  recommendation={recommendation}
                  requestId={data.request_id}
                />
              ))}
            </div>
          )}

          {/* Under the ranked crops, because it is what happens after the
              decision rather than part of making it. */}
          <SeasonDiary data={data} />
        </>
      ),
    },
    // Directly after Dashboard, as the place a farmer comes back to.
    {
      id: 'saved',
      label: t('tabs.saved'),
      icon: Bookmark,
      content: <SavedPlansPanel />,
    },
    {
      id: 'water',
      label: t('tabs.water'),
      icon: Droplets,
      content: <WaterPanel budgets={data.water} irrigation={data.request_echo?.irrigation} />,
    },
    {
      // Its own tab rather than a card under Planning. The two signals here
      // are about the market and the advice, not about this field, and every
      // number carries a caveat that needs room to be read rather than
      // skimmed past on the way to something else.
      id: 'crowding',
      label: t('tabs.crowding'),
      icon: Users,
      content: <CrowdingPanel crowding={data.crowding} />,
    },
    {
      // Risk and the what-if calculator answer the same question from two
      // directions: what could go wrong, and what would happen if you changed
      // something. They belong together.
      id: 'planning',
      label: t('tabs.planning'),
      icon: ShieldAlert,
      content: (
        <>
          <RiskPanel risk={data.risk} />
          <ImpactCalculator result={data} />
        </>
      ),
    },
    // Three reference tabs. Nothing here is computed from this field — they
    // restate what the Government of India and the RBI publish and link out.
    // Grouped after Risk & planning because that is where a farmer who has
    // just seen a money figure starts asking "what protects me if this goes
    // wrong, and who lends against it".
    {
      id: 'msp',
      label: t('tabs.msp'),
      icon: IndianRupee,
      content: <MspPanel />,
    },
    {
      id: 'psl',
      label: t('tabs.psl'),
      icon: Landmark,
      content: (
        <>
          <PslPanel />
          <CreditApplySection />
        </>
      ),
    },
    {
      id: 'schemes',
      label: t('tabs.schemes'),
      icon: FileText,
      content: <SchemesPanel />,
    },
    // The farmer's year in order: buy the inputs, hire what you cannot buy,
    // find a buyer, then sell. None of these tabs transact — they point at
    // where others do.
    {
      id: 'inputs',
      label: t('tabs.inputs'),
      icon: ShoppingCart,
      content: <InputsPanel />,
    },
    {
      id: 'rental',
      label: t('tabs.rental'),
      icon: Tractor,
      content: <RentalPanel />,
    },
    {
      id: 'buyers',
      label: t('tabs.buyers'),
      icon: Handshake,
      content: <BuyersPanel />,
    },
    // Last, because it is the last thing that happens: the crop is grown and
    // then it has to be sold. Where it is sold moves the price more than most
    // of the agronomic decisions above it.
    {
      id: 'emandi',
      label: t('tabs.emandi'),
      icon: Store,
      content: <EmandiPanel />,
    },
  ];

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <PrintHeader data={data} />

      <div className="no-print">
        <Link
          href="/"
          className="on-canvas-muted inline-flex items-center gap-1.5 text-sm transition-colors hover:text-white"
        >
          <ArrowLeft className="h-4 w-4" aria-hidden />
          {t('actions.changeField')}
        </Link>

        <div className="mt-3 flex flex-wrap items-start justify-between gap-3">
          <h1 className="on-canvas text-2xl font-semibold tracking-tight">
            {t('results.title', { district: place.district_name })}
          </h1>
          <div className="flex flex-wrap gap-2">
            {/* Beside the print button, because both are ways of taking the
                advisory away from the screen. */}
            <SavePlanButton data={data} />
            <ListenButton data={data} />
            <PrintAdvisoryButton />
          </div>
        </div>
        <p className="on-canvas-muted text-sm">
          {t('results.meta', {
            area: formatNumber(place.area_ha, 'ha'),
            state: place.state_code,
            timestamp: formatTimestamp(data.generated_at),
          })}
        </p>
      </div>

      {/* Warnings sit ABOVE the tabs, not inside one.
          They qualify the whole result — a closed sowing window or provisional
          thresholds apply just as much while reading the water budget as the
          ranking. Filing them under Dashboard would let a farmer miss them by
          landing on another tab. */}
      <PrecisionNotice location={place} />

      <WarningsList warnings={data.warnings} />

      <ResultTabs tabs={sections} />

      {/* Paper has nowhere to tap, so everything the farmer would have drilled
          into is printed inline. */}
      <PrintCropDetail data={data} />

      <p className="on-canvas-muted text-xs">{t('results.scoreCaveat')}</p>

      <p className="on-canvas-muted no-print text-xs">{t('print.hint')}</p>

      <PrintFooter />

      {/* Floating, and only here: it answers about THIS advisory. */}
      <ChatBox requestId={data.request_id} />
    </div>
  );
}
