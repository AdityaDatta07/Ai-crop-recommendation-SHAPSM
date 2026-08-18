import type { Money } from '@/types/api';

/**
 * Display only. No arithmetic lives here and none should be added.
 * api-contract.md section 4: null means "not available", and renders as a dash.
 */

export const NOT_AVAILABLE = '—'; // em dash

const inr = new Intl.NumberFormat('en-IN', {
  style: 'currency',
  currency: 'INR',
  maximumFractionDigits: 0,
});

const decimal = new Intl.NumberFormat('en-IN', { maximumFractionDigits: 2 });

export function formatMoney(value: Money | null | undefined): string {
  if (value === null || value === undefined) return NOT_AVAILABLE;
  return inr.format(value);
}

export function formatNumber(value: number | null | undefined, unit?: string): string {
  if (value === null || value === undefined) return NOT_AVAILABLE;
  return unit ? `${decimal.format(value)} ${unit}` : decimal.format(value);
}

export function formatPercent(value: number | null | undefined): string {
  if (value === null || value === undefined) return NOT_AVAILABLE;
  return `${Math.round(value * 100)}%`;
}

/** ISO date -> "15 Nov 2026". Returns the input unchanged if unparseable. */
export function formatDate(iso: string | null | undefined): string {
  if (!iso) return NOT_AVAILABLE;
  const date = new Date(`${iso}T00:00:00Z`);
  if (Number.isNaN(date.getTime())) return iso;
  return new Intl.DateTimeFormat('en-IN', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
    timeZone: 'UTC',
  }).format(date);
}

export function formatDateRange(start?: string | null, end?: string | null): string {
  if (!start || !end) return NOT_AVAILABLE;
  return `${formatDate(start)} - ${formatDate(end)}`;
}

export function formatTimestamp(iso: string | null | undefined): string {
  if (!iso) return NOT_AVAILABLE;
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return new Intl.DateTimeFormat('en-IN', {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(date);
}

const FACTOR_LABELS: Record<string, string> = {
  soil_ph: 'Soil pH',
  soil_texture: 'Soil texture',
  nitrogen: 'Nitrogen',
  rainfall: 'Rainfall',
  temperature: 'Temperature',
  irrigation: 'Irrigation',
  market_price: 'Market price',
  season_fit: 'Season fit',
  rotation: 'Crop rotation',
};

export function factorLabel(factor: string): string {
  return FACTOR_LABELS[factor] ?? factor.replace(/_/g, ' ');
}

export function titleCase(value: string | null | undefined): string {
  if (!value) return NOT_AVAILABLE;
  return value.charAt(0).toUpperCase() + value.slice(1);
}
