import { useState } from 'react';
import type { CompareResponse } from '@contracts';
import { compare } from '../lib/api';
import { formatCents, formatRange } from '../lib/format';
import { Flags } from '../components/Flags';
import { Disclaimer } from '../components/Disclaimer';

interface CompareProps {
  onBack: () => void;
}

/**
 * Compare / price-lookup screen. This also reserves the slot for the chart
 * component built separately (ND); see <div className="chart-slot">.
 */
export function Compare({ onBack }: CompareProps) {
  const [code, setCode] = useState('');
  const [charged, setCharged] = useState('');
  const [result, setResult] = useState<CompareResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function lookup() {
    setError(null);
    const cents = Math.round(Number(charged.replace(/[$,]/g, '')) * 100);
    if (!code.trim() || Number.isNaN(cents)) {
      setError('Enter a billing code and the amount you were charged.');
      return;
    }
    setBusy(true);
    try {
      setResult(await compare(code.trim(), cents));
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not look that up.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <section aria-labelledby="compare-heading">
      <h1 id="compare-heading">Look up a price</h1>
      <Disclaimer />
      <p className="lede">
        Enter a billing code and what you were charged to see reference prices.
      </p>

      <div className="card">
        <label htmlFor="cmp-code">Billing code</label>
        <input
          id="cmp-code"
          value={code}
          onChange={(e) => setCode(e.target.value)}
          placeholder="e.g. 99213"
        />
        <label htmlFor="cmp-charged">Amount you were charged (USD)</label>
        <input
          id="cmp-charged"
          inputMode="decimal"
          value={charged}
          onChange={(e) => setCharged(e.target.value)}
          placeholder="e.g. 300.00"
        />
        <div className="actions">
          <button type="button" onClick={lookup} disabled={busy}>
            {busy ? 'Looking…' : 'Compare'}
          </button>
        </div>
      </div>

      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}

      {result && (
        <div className="card">
          <h2>Code {result.code}</h2>
          <dl className="result-meta">
            <div>
              <dt>You were charged</dt>
              <dd>{formatCents(result.charged)}</dd>
            </div>
            <div>
              <dt>Medicare reference</dt>
              <dd>{formatCents(result.medicare_reference)}</dd>
            </div>
            <div>
              <dt>Typical MA range</dt>
              <dd>
                {formatRange(
                  result.ma_price_range?.low ?? null,
                  result.ma_price_range?.high ?? null,
                )}
              </dd>
            </div>
            <div>
              <dt>Compared with Medicare</dt>
              <dd>
                {result.ratio_to_medicare !== null
                  ? `${result.ratio_to_medicare}×`
                  : '—'}
              </dd>
            </div>
          </dl>
          <Flags flags={result.flags} />

          {/* Slot for the comparison chart component (built separately by ND). */}
          <div className="chart-slot" aria-hidden="true" />
        </div>
      )}

      <div className="actions">
        <button type="button" className="link" onClick={onBack}>
          Back
        </button>
      </div>
    </section>
  );
}
