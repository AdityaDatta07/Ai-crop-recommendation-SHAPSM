'use client';

import { RecommendationForm } from '@/components/recommendation/recommendation-form';
import { useTranslation } from '@/i18n/provider';

export default function HomePage() {
  const t = useTranslation();

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div className="space-y-2">
        <h1 className="text-2xl font-semibold tracking-tight">{t('home.title')}</h1>
        <p className="text-muted-foreground">{t('home.subtitle')}</p>
      </div>

      <RecommendationForm />
    </div>
  );
}
