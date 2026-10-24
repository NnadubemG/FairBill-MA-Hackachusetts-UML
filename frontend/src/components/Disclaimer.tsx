/**
 * The "Guidance only" note. Required to be visible on every results screen.
 * Uses neutral, non-advice language (see product.md).
 */
export function Disclaimer() {
  return (
    <aside className="disclaimer" role="note" aria-label="Guidance only notice">
      <strong>General information only.</strong> This tool can help you understand
      what the bill shows. It cannot decide the amount you may be responsible for or
      make decisions for you. Please confirm important details with your provider,
      insurer, or an official Massachusetts source before acting.
    </aside>
  );
}
