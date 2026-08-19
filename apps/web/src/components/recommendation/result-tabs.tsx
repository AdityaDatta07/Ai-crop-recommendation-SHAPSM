'use client';

import { useState } from 'react';
import type { LucideIcon } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useTranslation } from '@/i18n/provider';

/**
 * Sectioned navigation for a results page that had grown to seven panels.
 *
 * HIDDEN, NOT UNMOUNTED — AND THE REASON MATTERS
 * -----------------------------------------------
 * Every panel stays in the DOM. Inactive ones are hidden with CSS, which the
 * print stylesheet then overrides.
 *
 * Conditional rendering would have been the obvious implementation and would
 * have quietly broken the advisory PDF: a farmer on the Dashboard tab pressing
 * "Download advisory" would have got a document with no water budget and no
 * risk section, with nothing anywhere to say they were missing. The printed
 * sheet is the artefact that leaves the building — it has to carry everything
 * regardless of which tab happened to be open.
 *
 * The same choice keeps the browser's find-in-page working across sections,
 * which is how anyone actually looks for a number.
 *
 * ON SMALL SCREENS
 * ----------------
 * A left rail is a desktop idea. Most of the people this is built for are on a
 * phone, so below `md` the rail becomes a horizontally scrollable strip above
 * the content and the layout goes back to a single column.
 */

export interface ResultTab {
  id: string;
  label: string;
  icon: LucideIcon;
  content: React.ReactNode;
  /** Shown as a small count or flag beside the label, e.g. unread warnings. */
  badge?: number;
}

export function ResultTabs({ tabs }: { tabs: ResultTab[] }) {
  const t = useTranslation();
  const [active, setActive] = useState(tabs[0]?.id);

  return (
    <div className="gap-6 md:flex md:items-start">
      <nav
        aria-label={t('tabs.label')}
        className={cn(
          'no-print',
          // Phone: a scrollable strip. Desktop: a sticky rail that stays put
          // while a long panel scrolls beside it.
          '-mx-4 flex gap-1 overflow-x-auto px-4 pb-2',
          'md:mx-0 md:w-56 md:shrink-0 md:flex-col md:overflow-visible md:px-0 md:pb-0',
          'md:sticky md:top-6',
        )}
      >
        {tabs.map((tab) => {
          const Icon = tab.icon;
          const selected = tab.id === active;

          return (
            <button
              key={tab.id}
              type="button"
              onClick={() => setActive(tab.id)}
              aria-current={selected ? 'page' : undefined}
              className={cn(
                'flex shrink-0 items-center gap-2 rounded-lg px-3 py-2 text-sm transition-colors',
                'md:w-full md:shrink',
                selected
                  ? 'bg-gradient-to-r from-emerald-500 to-green-600 text-white shadow-lg shadow-emerald-950/40'
                  : 'text-emerald-100/70 hover:bg-white/10 hover:text-white',
              )}
            >
              <Icon className="h-4 w-4 shrink-0" aria-hidden />
              <span className="whitespace-nowrap md:whitespace-normal md:text-left">
                {tab.label}
              </span>
              {tab.badge !== undefined && tab.badge > 0 && (
                <span
                  className={cn(
                    'ml-auto rounded-full px-1.5 text-xs tabular-nums',
                    selected ? 'bg-white/25' : 'bg-white/10 text-emerald-50',
                  )}
                >
                  {tab.badge}
                </span>
              )}
            </button>
          );
        })}
      </nav>

      <div className="min-w-0 flex-1 space-y-6">
        {tabs.map((tab) => (
          <section
            key={tab.id}
            // `hidden` rather than unmounting. print.css reveals all of these.
            hidden={tab.id !== active}
            data-result-section
            aria-label={tab.label}
            className="space-y-6"
          >
            {tab.content}
          </section>
        ))}
      </div>
    </div>
  );
}
