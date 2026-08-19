'use client';

import { RecommendationForm } from '@/components/recommendation/recommendation-form';
import { useTranslation } from '@/i18n/provider';

export default function HomePage() {
  const t = useTranslation();

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      {/* Sits on the dark canvas, not in a card. */}
      <div className="space-y-2 py-2">
        <h1 className="on-canvas text-3xl font-semibold tracking-tight sm:text-4xl">
          {t('home.title')}
        </h1>
        <p className="on-canvas-muted max-w-2xl text-base">{t('home.subtitle')}</p>
      </div>

      <RecommendationForm />
    </div>
  );
}
