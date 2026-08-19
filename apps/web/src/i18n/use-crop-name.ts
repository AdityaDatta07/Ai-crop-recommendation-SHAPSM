'use client';

import { useCallback } from 'react';
import { useCrops } from '@/lib/queries';
import { useI18n } from './provider';

/**
 * The localised name of a crop.
 *
 * `name_hi` has been in the API since the reference data was written and was
 * never read: every crop name in the UI rendered as English, so a farmer on the
 * Hindi setting saw "Pigeon pea" sitting under a Hindi heading.
 *
 * Names come from data/reference/crops.yaml through the crops endpoint rather
 * than from these dictionaries, so there is one list of crops and not two.
 * Falls back to whatever English name the caller already has, which is right
 * both before the query resolves and for any crop without a translation.
 */
export function useCropName() {
  const { locale } = useI18n();
  const { data } = useCrops();

  return useCallback(
    (cropCode: string | undefined, fallback: string): string => {
      if (!cropCode || locale === 'en') return fallback;
      const crop = data?.crops.find(
        (item) => item.crop_code.toUpperCase() === cropCode.toUpperCase(),
      );
      // `names` first, `name_hi` only as the older field for Hindi. Falling
      // back to the English name is right both before the query resolves and
      // for any crop this language has no name for — a visible English word
      // beats a blank where a crop name should be.
      return crop?.names?.[locale] || (locale === 'hi' ? crop?.name_hi : undefined) || fallback;
    },
    [data, locale],
  );
}
