import { useEffect, useState } from 'react';
import type { AnalysisResult, LineItem } from '@contracts';
import { analyze } from '../lib/api';
import { formatCents, formatRange } from '../lib/format';
import { Flags } from '../components/Flags';
import { Disclaimer } from '../components/Disclaimer';
import { Resources } from '../components/Resources';

interface ResultsProps {
  items: LineItem[];
  onGoToLetter: () => void;
  onBack: () => void;
}

export function Results({ items, onGoToLetter, onBack }: ResultsProps) {
  const [results, setResults] = useState<AnalysisResult[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    analyze({ line_items: items })
      .then((r) => active && setResults(r.results))
      .catch(
        (e) =>
          active &&
          setError(e instanceof Error ? e.message : 'Could not analyze the bill.'),
      );
    return () => {
      active = false;
    };
  }, [items]);

  const anyFlags = results?.some((r) => r.flags.length) ?? false;

  return (
    <section aria-labelledby="results-heading">
      <h1 id="results-heading">What your bill says</h1>
      <Disclaimer />

      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {!results && !error && <p role="status">Looking things over…</p>}

      {results && (
        <>
          <div className="result-cards">
            {results.map((r) => {
              const item = items[r.line_index];
              return (
                <article className="result-card" key={r.line_index}>
                  <h2>{r.plain_language_label}</h2>
                  <dl className="result-meta">
                    <div>
                      <dt>You were charged</dt>
                      <dd>{formatCents(item?.charge ?? null)}</dd>
                    </div>
                    <div>
                      <dt>Medicare reference</dt>
                      <dd>{formatCents(r.medicare_reference)}</dd>
                    </div>
                    <div>
                      <dt>Typical MA range</dt>
                      <dd>
                        {formatRange(
                          r.ma_price_range?.low ?? null,
                          r.ma_price_range?.high ?? null,
                        )}
                      </dd>
                    </div>
                  </dl>
                  <Flags flags={r.flags} />
                </article>
              );
            })}
          </div>

          <section className="summary" aria-labelledby="ask-heading">
            <h2 id="ask-heading">What you might ask the billing office</h2>
            <ul>
              <li>Ask for a fully itemized bill if you don’t already have one.</li>
              {anyFlags && (
                <li>
                  Ask about the lines we flagged above — for example, how a charge
                  was calculated or whether a service appears more than once.
                </li>
              )}
              <li>
                Ask whether financial assistance or a payment plan is available.
              </li>
            </ul>
            <div className="actions">
              <button type="button" className="link" onClick={onBack}>
                Back
              </button>
              <button type="button" onClick={onGoToLetter}>
                Draft a letter
              </button>
            </div>
          </section>

          <Resources />
        </>
      )}
    </section>
  );
}
