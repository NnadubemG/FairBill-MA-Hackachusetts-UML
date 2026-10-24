/** Formatting helpers. Money is whole US cents per the contracts. */

export function formatCents(cents: number | null | undefined): string {
  if (cents === null || cents === undefined) return '—';
  return (cents / 100).toLocaleString('en-US', {
    style: 'currency',
    currency: 'USD',
  });
}

export function formatRange(
  low: number | null | undefined,
  high: number | null | undefined,
): string {
  if ((low === null || low === undefined) && (high === null || high === undefined)) {
    return '—';
  }
  return `${formatCents(low)} – ${formatCents(high)}`;
}

export function formatConfidence(c: number): string {
  return `${Math.round(c * 100)}%`;
}
