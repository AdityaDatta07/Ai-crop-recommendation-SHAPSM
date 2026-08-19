'use client';

import { useEffect, useRef, useState } from 'react';
import { Mic, Loader2 } from 'lucide-react';
import { cn } from '@/lib/utils';
import { listenOnce, speechRecognitionSupported } from '@/lib/speech';
import { useI18n } from '@/i18n/provider';

/**
 * One button, one utterance.
 *
 * IT RENDERS NOTHING WHERE IT WOULD NOT WORK
 * ------------------------------------------
 * Recognition is effectively Chrome-only. A microphone icon that does nothing
 * on Firefox is worse than no icon: it reads as a broken app rather than an
 * absent feature. The support check has to run in an effect, not during
 * render, or the server-rendered HTML (no `window`) and the first client render
 * disagree and React throws a hydration error.
 *
 * IT SAYS WHERE THE AUDIO GOES, AT THE MOMENT IT GOES
 * ---------------------------------------------------
 * Chrome streams recognition audio to Google's servers. Nothing about a
 * microphone icon suggests that, and a line in a privacy policy is not
 * disclosure to somebody who is being handed a phone in a field. So the note
 * appears while recording, every time, not once behind a dismiss button.
 *
 * IT NEVER FILLS A FIELD BY ITSELF
 * --------------------------------
 * The transcript goes to the caller, which decides what to do with it. Every
 * caller in this app shows the parsed value for confirmation rather than
 * committing it, because plot size becomes rupees and a district becomes a
 * soil sample. A mishearing that is silently accepted is the whole risk of
 * this feature.
 */
export function MicButton({
  onTranscript,
  label,
  className,
  disabled,
}: {
  onTranscript: (transcript: string) => void;
  /** Accessible name — "Say your district", not "Microphone". */
  label: string;
  className?: string;
  disabled?: boolean;
}) {
  const { t, locale } = useI18n();
  const [supported, setSupported] = useState(false);
  const [listening, setListening] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const abort = useRef<AbortController | null>(null);

  useEffect(() => {
    setSupported(speechRecognitionSupported());
    return () => abort.current?.abort();
  }, []);

  if (!supported) return null;

  async function start() {
    if (listening) {
      abort.current?.abort();
      return;
    }
    setProblem(null);
    setListening(true);
    abort.current = new AbortController();

    const result = await listenOnce(locale, abort.current.signal);
    setListening(false);

    if (result.ok) {
      onTranscript(result.transcript);
    } else if (result.reason !== 'no-speech') {
      // 'no-speech' covers both silence and the user cancelling. Neither is an
      // error worth a red message.
      setProblem(t(`voice.error.${result.reason}`));
    }
  }

  return (
    <div className={cn('no-print', className)}>
      <button
        type="button"
        onClick={start}
        disabled={disabled}
        aria-label={listening ? t('voice.stop') : label}
        aria-pressed={listening}
        className={cn(
          'inline-flex items-center gap-1.5 rounded-md border px-2.5 py-1 text-xs font-medium transition-colors',
          listening
            ? 'border-destructive/40 bg-destructive/10 text-destructive'
            : 'border-border text-muted-foreground hover:text-foreground',
          disabled && 'cursor-not-allowed opacity-50',
        )}
      >
        {listening ? (
          <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden />
        ) : (
          <Mic className="h-3.5 w-3.5" aria-hidden />
        )}
        {listening ? t('voice.listening') : t('voice.speak')}
      </button>

      {listening && (
        <p className="mt-1 text-xs text-muted-foreground" role="status">
          {t('voice.sentAway')}
        </p>
      )}

      {problem && (
        <p className="mt-1 text-xs text-destructive" role="status">
          {problem}
        </p>
      )}
    </div>
  );
}
