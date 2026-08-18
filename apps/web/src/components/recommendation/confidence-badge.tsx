'use client';

import { Badge } from '@/components/ui/badge';
import { useTranslation } from '@/i18n/provider';
import type { Confidence } from '@/types/api';

const VARIANT = {
  high: 'positive',
  medium: 'neutral',
  low: 'negative',
} as const;

export function ConfidenceBadge({ confidence }: { confidence: Confidence }) {
  const t = useTranslation();
  return (
    <Badge variant={VARIANT[confidence]} title="Derived from how much input data was available">
      {t('crop.confidence', { level: t(`crop.${confidence}`) })}
    </Badge>
  );
}
