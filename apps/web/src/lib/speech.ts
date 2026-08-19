/**
 * Web Speech, wrapped so the rest of the app never has to think about it.
 *
 * WHAT IS AND IS NOT SUPPORTED
 * ----------------------------
 * Recognition is effectively Chrome-only. Firefox has never shipped it, and
 * Safari's implementation is partial and iOS-version dependent. Synthesis is
 * near-universal but its VOICES are not: a device with no Hindi voice
 * installed will happily accept `lang: 'hi-IN'` and read Devanagari in an
 * English accent, or silently say nothing at all.
 *
 * So both helpers report support honestly and the UI hides what is missing.
 * Nothing here is ever the only way to do something — every field can be typed
 * and every result can be read.
 *
 * WHERE THE AUDIO GOES
 * --------------------
 * Chrome streams recognition audio to Google's servers. That is not obvious
 * from a microphone icon, so the component that uses this says so at the
 * moment recording starts rather than burying it in a policy nobody opens.
 *
 * OFFLINE
 * -------
 * Recognition needs the network. This app is built to work without one, so a
 * failed recording must read as "voice needs a connection" and not as a broken
 * feature.
 */

type SpeechRecognitionLike = {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  maxAlternatives: number;
  start: () => void;
  stop: () => void;
  abort: () => void;
  onresult: ((event: any) => void) | null;
  onerror: ((event: any) => void) | null;
  onend: (() => void) | null;
};

function recognitionConstructor(): (new () => SpeechRecognitionLike) | null {
  if (typeof window === 'undefined') return null;
  const w = window as unknown as Record<string, unknown>;
  return (w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null) as
    | (new () => SpeechRecognitionLike)
    | null;
}

export function speechRecognitionSupported(): boolean {
  return recognitionConstructor() !== null;
}

export function speechSynthesisSupported(): boolean {
  return typeof window !== 'undefined' && 'speechSynthesis' in window;
}

/**
 * BCP-47 tags. Every one is the Indian variant.
 *
 * en-IN rather than en-US because the vocabulary is local — "lakh", "mandi",
 * "kharif" — and a US voice mangles all of it.
 *
 * RECOGNITION AND SYNTHESIS COVERAGE ARE NOT THE SAME
 * ---------------------------------------------------
 * Chrome's recogniser handles all of these. Text-to-speech voices are far
 * patchier: a given phone may have Hindi and Tamil installed but not Gujarati.
 * `hasVoiceFor` is what stops the Listen button appearing when the voice is
 * missing, because `speechSynthesis.speak` does not fail in that case — it
 * substitutes an English voice and reads the script as noise.
 */
const SPEECH_LOCALES: Record<string, string> = {
  en: 'en-IN',
  hi: 'hi-IN',
  mr: 'mr-IN',
  bn: 'bn-IN',
  gu: 'gu-IN',
  ta: 'ta-IN',
  te: 'te-IN',
};

export function speechLocale(locale: string): string {
  return SPEECH_LOCALES[locale] ?? 'en-IN';
}

export type ListenResult =
  | { ok: true; transcript: string }
  | { ok: false; reason: 'unsupported' | 'denied' | 'offline' | 'no-speech' | 'failed' };

/**
 * Record one utterance and return what was heard.
 *
 * Single-shot rather than continuous. A farmer filling one field wants to say
 * one thing and be done; a listening microphone that never stops is both
 * unnerving and a battery cost.
 */
export function listenOnce(locale: string, signal?: AbortSignal): Promise<ListenResult> {
  const Recognition = recognitionConstructor();
  if (!Recognition) return Promise.resolve({ ok: false, reason: 'unsupported' });

  return new Promise((resolve) => {
    const recognition = new Recognition();
    recognition.lang = speechLocale(locale);
    recognition.continuous = false;
    recognition.interimResults = false;
    recognition.maxAlternatives = 1;

    let settled = false;
    const finish = (result: ListenResult) => {
      if (settled) return;
      settled = true;
      resolve(result);
    };

    recognition.onresult = (event) => {
      const transcript = event?.results?.[0]?.[0]?.transcript;
      finish(
        typeof transcript === 'string' && transcript.trim()
          ? { ok: true, transcript: transcript.trim() }
          : { ok: false, reason: 'no-speech' },
      );
    };

    recognition.onerror = (event) => {
      const code = event?.error;
      if (code === 'not-allowed' || code === 'service-not-allowed') {
        finish({ ok: false, reason: 'denied' });
      } else if (code === 'network') {
        finish({ ok: false, reason: 'offline' });
      } else if (code === 'no-speech' || code === 'aborted') {
        finish({ ok: false, reason: 'no-speech' });
      } else {
        finish({ ok: false, reason: 'failed' });
      }
    };

    // Fires even after a successful result, so it only matters as a backstop
    // for a recogniser that ends without ever calling onresult or onerror.
    recognition.onend = () => finish({ ok: false, reason: 'no-speech' });

    signal?.addEventListener('abort', () => {
      recognition.abort();
      finish({ ok: false, reason: 'no-speech' });
    });

    try {
      recognition.start();
    } catch {
      finish({ ok: false, reason: 'failed' });
    }
  });
}

/**
 * True only when a voice for this language is actually installed.
 *
 * `speechSynthesis.speak` does not fail when the language is unavailable — it
 * substitutes whatever voice it has, so Hindi gets read aloud by an English
 * voice as meaningless syllables. Offering a listen button that does that is
 * worse than offering none.
 */
export function hasVoiceFor(locale: string): boolean {
  if (!speechSynthesisSupported()) return false;
  const wanted = speechLocale(locale).toLowerCase();
  const language = wanted.split('-')[0];
  return window.speechSynthesis
    .getVoices()
    .some((voice) => voice.lang.toLowerCase().startsWith(language));
}

/**
 * `onEnd` fires when the utterance finishes, is cancelled, or errors.
 *
 * A caller showing a "stop" button needs all three, not just the happy one: a
 * button stuck on "stop" after the voice has finished is a control that lies
 * about what the page is doing.
 */
export function speak(text: string, locale: string, onEnd?: () => void): void {
  if (!speechSynthesisSupported()) {
    onEnd?.();
    return;
  }

  // Cancel first: queued utterances otherwise stack up and the farmer hears
  // the previous crop's advice before this one's.
  window.speechSynthesis.cancel();

  const utterance = new SpeechSynthesisUtterance(text);
  utterance.lang = speechLocale(locale);
  // Slightly slower than default. This is unfamiliar vocabulary, often heard
  // once, sometimes outdoors.
  utterance.rate = 0.95;

  const voice = window.speechSynthesis
    .getVoices()
    .find((candidate) => candidate.lang.toLowerCase().startsWith(speechLocale(locale).slice(0, 2)));
  if (voice) utterance.voice = voice;

  if (onEnd) {
    let done = false;
    const finish = () => {
      if (done) return;
      done = true;
      onEnd();
    };
    utterance.onend = finish;
    utterance.onerror = finish;
  }

  window.speechSynthesis.speak(utterance);
}

export function stopSpeaking(): void {
  if (speechSynthesisSupported()) window.speechSynthesis.cancel();
}
