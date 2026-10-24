import { useState } from 'react';
import type { LineItem } from '@contracts';
import { formatConfidence } from '../lib/format';

interface ConfirmProps {
  initial: LineItem[];
  onConfirmed: (items: LineItem[]) => void;
  onBack: () => void;
}

/**
 * Confirm screen: an editable table of extracted line items. Every field is
 * editable; rows needing confirmation are highlighted. The user must press
 * "Looks right" to continue.
 */
export function Confirm({ initial, onConfirmed, onBack }: ConfirmProps) {
  const [items, setItems] = useState<LineItem[]>(initial);

  function update(index: number, patch: Partial<LineItem>) {
    setItems((prev) =>
      prev.map((it, i) => (i === index ? { ...it, ...patch } : it)),
    );
  }

  function dollarsToCents(value: string): number | null {
    const trimmed = value.trim();
    if (trimmed === '') return null;
    const num = Number(trimmed.replace(/[$,]/g, ''));
    if (Number.isNaN(num)) return null;
    return Math.round(num * 100);
  }

  function centsToDollars(cents: number | null): string {
    return cents === null || cents === undefined ? '' : (cents / 100).toFixed(2);
  }

  return (
    <section aria-labelledby="confirm-heading">
      <h1 id="confirm-heading">Check what we found</h1>
      <p className="lede">
        Here’s what we read from your bill. Please check each line and fix anything
        that looks off. Highlighted rows are ones we’re less sure about.
      </p>

      <div className="table-wrap">
        <table className="line-items">
          <caption className="sr-only">
            Editable list of charges read from your bill
          </caption>
          <thead>
            <tr>
              <th scope="col">Code</th>
              <th scope="col">Description</th>
              <th scope="col">Units</th>
              <th scope="col">Charge</th>
              <th scope="col">Confidence</th>
            </tr>
          </thead>
          <tbody>
            {items.map((it, i) => (
              <tr key={i} className={it.needs_confirmation ? 'needs-confirm' : ''}>
                <td>
                  <label className="sr-only" htmlFor={`code-${i}`}>
                    Code for row {i + 1}
                  </label>
                  <input
                    id={`code-${i}`}
                    value={it.code ?? ''}
                    onChange={(e) =>
                      update(i, { code: e.target.value || null })
                    }
                  />
                </td>
                <td>
                  <label className="sr-only" htmlFor={`desc-${i}`}>
                    Description for row {i + 1}
                  </label>
                  <input
                    id={`desc-${i}`}
                    value={it.description}
                    onChange={(e) => update(i, { description: e.target.value })}
                  />
                </td>
                <td>
                  <label className="sr-only" htmlFor={`units-${i}`}>
                    Units for row {i + 1}
                  </label>
                  <input
                    id={`units-${i}`}
                    type="number"
                    min={0}
                    value={it.units}
                    onChange={(e) =>
                      update(i, { units: Math.max(0, Number(e.target.value) || 0) })
                    }
                  />
                </td>
                <td>
                  <label className="sr-only" htmlFor={`charge-${i}`}>
                    Charge in dollars for row {i + 1}
                  </label>
                  <input
                    id={`charge-${i}`}
                    inputMode="decimal"
                    value={centsToDollars(it.charge)}
                    onChange={(e) =>
                      update(i, { charge: dollarsToCents(e.target.value) })
                    }
                  />
                </td>
                <td>
                  {formatConfidence(it.confidence)}
                  {it.needs_confirmation && (
                    <span className="badge" title="Please double-check this row">
                      check
                    </span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="actions">
        <button type="button" className="link" onClick={onBack}>
          Back
        </button>
        <button type="button" onClick={() => onConfirmed(items)}>
          Looks right
        </button>
      </div>
    </section>
  );
}
