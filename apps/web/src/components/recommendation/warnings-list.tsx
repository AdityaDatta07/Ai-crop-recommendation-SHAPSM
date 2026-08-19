'use client';

import { AlertTriangle } from 'lucide-react';
import { useI18n } from '@/i18n/provider';
import { useServerText } from '@/i18n/use-server-text';
import type { Warning } from '@/types/api';

/**
 * Warnings are shown, never swallowed. A partial answer that hides its gaps is
 * worse than one that names them - architecture.md principles 2 and 5.
 *
 * The text comes from the server in English, so it is rendered through
 * renderServerText rather than printed directly: otherwise a farmer reading
 * Hindi gets a Hindi heading over an English warning, which is the half that
 * actually matters.
 */
export function WarningsList({ warnings }: { warnings: Warning[] }) {
  const { t } = useI18n();
  const serverText = useServerText();
  if (warnings.length === 0) return null;

  return (
    <div data-print-warning className="rounded-lg border border-amber-200 bg-amber-50 p-4">
      <div className="flex items-center gap-2 text-sm font-medium text-amber-900">
        <AlertTriangle className="h-4 w-4" aria-hidden />
        {t('results.warningHeading')}
      </div>
      <ul className="mt-2 space-y-1 text-sm text-amber-900">
        {warnings.map((warning) => (
          <li key={warning.code}>
            {serverText('warning', warning.code, warning.params, warning.message)}
          </li>
        ))}
      </ul>
    </div>
  );
}
