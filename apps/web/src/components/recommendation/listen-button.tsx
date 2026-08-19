'use client';

import { useEffect, useState } from 'react';
import { Volume2, Square } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useI18n } from '@/i18n/provider';
import { useCropName } from '@/i18n/use-crop-name';
import { advisoryScript, joinScript, renderPart } from '@/lib/advisory-speech';
import { hasVoiceFor, speak, stopSpeaking } from '@/lib/speech';
import type { RecommendationResponse } from '@/types/api';

/**
 * Reads the summary aloud.
 *
 * WHY THE VOICE CHECK IS NOT JUST `'speechSynthesis' in window`
 * -------------------------------------------------------------
 * `speak()` does not fail when the requested language has no voice installed.
 * It substitutes whatever it has, so a Hindi advisory on a device with only
 * English voices is read as Devanagari-shaped noise — audibly broken, and
 * indistinguishable to the listener from the app being wrong. `hasVoiceFor`
 * is what stops us offering that.
 *
 * WHY THE CHECK IS DEFERRED
 * -------------------------
 * `getVoices()` returns an empty array on first call in Chrome and fills in
 * asynchronously, so a check at mount alone would hide the button on exactly
 * the browser this feature exists for. We listen for `voiceschanged` too.
 *
 * WHAT IT SAYS
 * ------------
 * See lib/advisory-speech.ts. Short, and it always ends by pointing at the
 * warnings on screen.
 */
export function ListenButton({ data }: { data: RecommendationResponse }) {
  const { t, locale } = useI18n();
  const cropName = useCropName();
  const [available, setAvailable] = useState(false);
  const [speaking, setSpeaking] = useState(false);

  useEffect(() => {
    const check = () => setAvailable(hasVoiceFor(locale));
    check();

    if (typeof window === 'undefined' || !('speechSynthesis' in window)) return;
    window.speechSynthesis.addEventListener('voiceschanged', check);
    return () => {
      window.speechSynthesis.removeEventListener('voiceschanged', check);
      // Leaving the page mid-sentence otherwise keeps talking, because
      // speechSynthesis is global to the tab and outlives this component.
      stopSpeaking();
    };
  }, [locale]);

  if (!available) return null;

  function toggle() {
    if (speaking) {
      stopSpeaking();
      setSpeaking(false);
      return;
    }
    const script = advisoryScript(data, cropName);
    setSpeaking(true);
    // Without the callback the button stays on "stop" after the voice has
    // finished, and the next press does nothing visible.
    speak(joinScript(script.map((part) => renderPart(part, t))), locale, () =>
      setSpeaking(false),
    );
  }

  return (
    <Button type="button" variant="outline" onClick={toggle} className="no-print">
      {speaking ? (
        <Square className="h-4 w-4" aria-hidden />
      ) : (
        <Volume2 className="h-4 w-4" aria-hidden />
      )}
      {speaking ? t('voice.stopReading') : t('voice.listen')}
    </Button>
  );
}
