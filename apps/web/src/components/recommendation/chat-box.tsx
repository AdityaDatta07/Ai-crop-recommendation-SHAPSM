'use client';

import { useEffect, useRef, useState } from 'react';
import { MessageCircle, X, Send, Loader2, ShieldAlert, Info } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useI18n } from '@/i18n/provider';
import { useServerText } from '@/i18n/use-server-text';
import { api } from '@/lib/client';
import type { ChatResponse } from '@/types/api';

/**
 * A question box in the corner of the results page.
 *
 * WHY IT LIVES ONLY ON A RESULTS PAGE
 * -----------------------------------
 * It answers about ONE advisory. There is no general assistant here, and the
 * absence is the point: the server fetches the grounding document by
 * request_id, so there is no conversation to have until an advisory exists.
 *
 * WHAT THE UI HAS TO CARRY THAT THE API ALREADY DECIDED
 * -----------------------------------------------------
 * `source` on every reply is the honesty dial, and each value looks different
 * on purpose:
 *
 *   template  — plain. Computed from the advisory; as trustworthy as the page.
 *   refusal   — amber, with a shield. Not a failure; a boundary, explained.
 *   model     — carries a visible "generated answer" note. A farmer cannot tell
 *               generated prose from computed prose by looking, so the page has
 *               to tell them.
 *   unavailable — says what went wrong and what still works.
 *
 * Rendering all four identically would be the easy version and would quietly
 * launder model output into the same visual authority as a figure traced to a
 * PIB release.
 */

interface Turn {
  role: 'user' | 'assistant';
  text?: string;
  response?: ChatResponse;
}

export function ChatBox({ requestId }: { requestId: string }) {
  const { t, locale } = useI18n();
  const serverText = useServerText();
  const [open, setOpen] = useState(false);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [draft, setDraft] = useState('');
  const [pending, setPending] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    // Keep the newest turn in view without yanking the whole page.
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
  }, [turns, pending]);

  async function send(question: string) {
    const message = question.trim();
    if (!message || pending) return;

    setTurns((previous) => [...previous, { role: 'user', text: message }]);
    setDraft('');
    setPending(true);

    try {
      // `turn` lets the server enforce its session cap. Counting user turns
      // rather than array length, so a failed round trip does not consume one
      // of the farmer's questions.
      const response = await api.askAboutAdvisory(
        requestId,
        message,
        turns.filter((turn) => turn.role === 'user').length + 1,
      );
      setTurns((previous) => [...previous, { role: 'assistant', response }]);
    } catch {
      setTurns((previous) => [
        ...previous,
        { role: 'assistant', response: { source: 'unavailable', code: 'model_error' } },
      ]);
    } finally {
      setPending(false);
    }
  }

  /** Resolve one reply into the text actually shown. */
  function render(response: ChatResponse): string {
    if (response.source === 'model') return response.text ?? '';

    const params: Record<string, unknown> = { ...response.params };
    // `factors` arrives as comma-joined factor keys. They have to be
    // translated individually — pasting the raw keys would put "soil_ph" in
    // the middle of a Hindi sentence.
    if (typeof params.factors === 'string' && params.factors) {
      params.factors = params.factors
        .split(',')
        .filter(Boolean)
        .map((key) => t(`factors.${key}`))
        .join(', ');
    }
    return serverText('chat', response.code, params, '');
  }

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="no-print fixed bottom-5 right-5 z-40 flex items-center gap-2 rounded-full bg-gradient-to-br from-emerald-500 to-green-600 px-5 py-3 font-medium text-white shadow-xl shadow-emerald-950/40 transition-transform hover:scale-105"
      >
        <MessageCircle className="h-5 w-5" aria-hidden />
        {t('chat.open')}
      </button>
    );
  }

  return (
    <div className="no-print fixed bottom-5 right-5 z-40 flex h-[min(34rem,80vh)] w-[min(26rem,calc(100vw-2.5rem))] flex-col overflow-hidden rounded-2xl border border-black/10 bg-white shadow-2xl shadow-emerald-950/50">
      <header className="flex items-center justify-between gap-2 bg-gradient-to-r from-emerald-600 to-green-700 px-4 py-3 text-white">
        <span className="flex items-center gap-2 font-medium">
          <MessageCircle className="h-4 w-4" aria-hidden />
          {t('chat.title')}
        </span>
        <button type="button" onClick={() => setOpen(false)} aria-label={t('chat.close')}>
          <X className="h-5 w-5" aria-hidden />
        </button>
      </header>

      <div ref={scrollRef} className="flex-1 space-y-3 overflow-y-auto p-4">
        {/* Says up front what it will not do, so a refusal later is a
            reminder rather than a surprise. */}
        <p className="flex items-start gap-2 rounded-lg bg-muted p-3 text-xs text-muted-foreground">
          <Info className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
          {t('chat.intro')}
        </p>

        {turns.map((turn, index) =>
          turn.role === 'user' ? (
            <p
              key={index}
              className="ml-auto max-w-[85%] rounded-2xl rounded-br-sm bg-emerald-600 px-3 py-2 text-sm text-white"
            >
              {turn.text}
            </p>
          ) : (
            <div key={index} className="max-w-[92%] space-y-1">
              {turn.response?.source === 'refusal' && (
                <p className="flex items-center gap-1.5 text-xs font-medium text-amber-700">
                  <ShieldAlert className="h-3.5 w-3.5" aria-hidden />
                  {t('chat.refusedBadge')}
                </p>
              )}
              {turn.response?.source === 'unavailable' &&
                turn.response.code === 'model_unverified' && (
                  <p className="text-xs font-medium text-amber-700">{t('chat.unverifiedBadge')}</p>
                )}
              <p
                className={cn(
                  'rounded-2xl rounded-bl-sm px-3 py-2 text-sm',
                  turn.response?.source === 'refusal'
                    ? 'border border-amber-200 bg-amber-50 text-amber-900'
                    : 'bg-secondary text-secondary-foreground',
                )}
              >
                {turn.response ? render(turn.response) : ''}
              </p>
              {/* Generated prose is visually indistinguishable from computed
                  prose, so it gets a label rather than trusting the reader to
                  guess which they are looking at. */}
              {turn.response?.source === 'model' && (
                <p className="text-xs text-muted-foreground">{t('chat.modelBadge')}</p>
              )}
            </div>
          ),
        )}

        {pending && (
          <p className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
            {t('chat.thinking')}
          </p>
        )}

        {turns.length === 0 && (
          <div className="flex flex-wrap gap-1.5">
            {['suggestion1', 'suggestion2', 'suggestion3'].map((key) => (
              <button
                key={key}
                type="button"
                onClick={() => send(t(`chat.${key}`))}
                className="rounded-full border border-border px-3 py-1 text-xs text-muted-foreground transition-colors hover:border-emerald-500 hover:text-foreground"
              >
                {t(`chat.${key}`)}
              </button>
            ))}
          </div>
        )}
      </div>

      <form
        onSubmit={(event) => {
          event.preventDefault();
          void send(draft);
        }}
        className="flex items-center gap-2 border-t border-border p-3"
      >
        <input
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          placeholder={t('chat.placeholder')}
          aria-label={t('chat.title')}
          lang={locale}
          maxLength={1000}
          className="min-w-0 flex-1 rounded-lg border border-input bg-background px-3 py-2 text-sm outline-none focus:border-emerald-500"
        />
        <button
          type="submit"
          disabled={pending || !draft.trim()}
          aria-label={t('chat.send')}
          className="rounded-lg bg-emerald-600 p-2 text-white disabled:opacity-40"
        >
          <Send className="h-4 w-4" aria-hidden />
        </button>
      </form>
    </div>
  );
}
