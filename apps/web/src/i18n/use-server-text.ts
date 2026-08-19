'use client';

import { useMemo } from 'react';
import { useCrops } from '@/lib/queries';
import { useI18n } from './provider';
import { renderServerText, type ServerTextGroup } from './server-text';

/**
 * Renders server-generated prose in the reader's language.
 *
 * Wraps renderServerText with the two things every call site would otherwise
 * have to assemble itself: the current locale, and the crop code -> localised
 * name map from the crops endpoint. That query is already cached by React
 * Query, so using this hook in several components costs one request.
 *
 *   const serverText = useServerText();
 *   serverText('warning', w.code, w.params, w.message);
 *
 * If the crops query has not resolved yet, crop names stay as the English the
 * server sent and correct themselves on the next render. A brief English crop
 * name is better than a blank where a crop name should be.
 */
export function useServerText() {
  const { locale } = useI18n();
  const { data } = useCrops();

  const cropNames = useMemo(() => {
    const map: Record<string, string> = {};
    for (const crop of data?.crops ?? []) {
      // name_hi comes from data/reference/crops.yaml, so the Hindi crop names
      // have one home rather than being duplicated into the i18n files.
      const localised =
        crop.names?.[locale] || (locale === 'hi' ? crop.name_hi : null) || null;
      map[crop.crop_code.toUpperCase()] = localised || crop.name;
    }
    return map;
  }, [data, locale]);

  return useMemo(
    () =>
      (
        group: ServerTextGroup,
        code: string | undefined,
        params: Record<string, unknown> | undefined,
        fallback: string,
      ) =>
        renderServerText(locale, group, code, params, fallback, cropNames),
    [locale, cropNames],
  );
}
