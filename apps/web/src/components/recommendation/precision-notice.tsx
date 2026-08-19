'use client';

import Link from 'next/link';
import { MapPin, ArrowRight } from 'lucide-react';
import { useTranslation } from '@/i18n/provider';
import type { ResolvedLocation } from '@/types/api';

/**
 * Says whose land the satellite actually looked at.
 *
 * THE PROBLEM
 * -----------
 * Every satellite figure in this app is read from a buffer around the resolved
 * centroid. Pick a district from the dropdown and that centroid is the
 * district's own — for Lucknow, the middle of Lucknow city. The soil, the NDVI,
 * the crop history and the productivity comparison are then all accurate
 * readings of a town, rendered identically to readings of a field.
 *
 * The symptom was a farmer being told their plot grew no crop and sat in the
 * 17th percentile of the surrounding farmland. Both figures were correct. The
 * plot was a city.
 *
 * Nothing about that is visible without this notice, which is what makes it
 * dangerous: the page looks the same either way.
 */
export function PrecisionNotice({ location }: { location?: ResolvedLocation | null }) {
  const t = useTranslation();

  // A drawn boundary or a dropped pin is a real reading of real land. Only the
  // district fallback needs explaining.
  if (!location || location.precision !== 'district') return null;

  return (
    <div
      data-print-warning
      className="rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900"
    >
      <p className="flex items-start gap-2">
        <MapPin className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
        <span>{t('precision.district', { district: location.district_name })}</span>
      </p>
      <Link
        href="/"
        className="no-print mt-2 inline-flex items-center gap-1.5 font-medium hover:underline"
      >
        {t('precision.action')}
        <ArrowRight className="h-3.5 w-3.5" aria-hidden />
      </Link>
    </div>
  );
}
