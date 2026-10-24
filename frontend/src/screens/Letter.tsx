import { useState } from 'react';
import type { LetterRequest, LetterType, LetterRecipient, LineItem } from '@contracts';
import { letter as draftLetter } from '../lib/api';
import { Disclaimer } from '../components/Disclaimer';

interface LetterProps {
  items: LineItem[];
  onBack: () => void;
}

const LETTER_TYPES: { value: LetterType; label: string }[] = [
  { value: 'itemized_bill_request', label: 'Request an itemized bill' },
  { value: 'billing_question', label: 'Ask a question about a charge' },
  { value: 'charge_dispute', label: 'Dispute a specific charge' },
  { value: 'insurance_appeal', label: 'Appeal an insurance decision' },
  { value: 'financial_assistance_request', label: 'Ask about financial assistance' },
];

export function Letter({ items, onBack }: LetterProps) {
  const [type, setType] = useState<LetterType>('itemized_bill_request');
  const [recipient, setRecipient] = useState<LetterRecipient>('provider');
  const [context, setContext] = useState('');
  const [subject, setSubject] = useState('');
  const [body, setBody] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  async function generate() {
    setError(null);
    setBusy(true);
    try {
      const req: LetterRequest = {
        type,
        recipient,
        line_items: items.length ? items : undefined,
        context: context.trim() || undefined,
      };
      const res = await draftLetter(req);
      setSubject(res.letter.subject);
      setBody(res.letter.body);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not draft the letter.');
    } finally {
      setBusy(false);
    }
  }

  async function copyToClipboard() {
    const text = `Subject: ${subject}\n\n${body}`;
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      setError('Could not copy. You can select the text and copy it manually.');
    }
  }

  return (
    <section aria-labelledby="letter-heading">
      <h1 id="letter-heading">Draft a letter</h1>
      <Disclaimer />
      <p className="lede">
        Choose what you’d like to say. We’ll draft a polite letter you can edit,
        then copy or print and send yourself. We never send anything for you.
      </p>

      <div className="card">
        <label htmlFor="letter-type">What do you want to do?</label>
        <select
          id="letter-type"
          value={type}
          onChange={(e) => setType(e.target.value as LetterType)}
        >
          {LETTER_TYPES.map((t) => (
            <option key={t.value} value={t.value}>
              {t.label}
            </option>
          ))}
        </select>

        <label htmlFor="letter-recipient">Who is it for?</label>
        <select
          id="letter-recipient"
          value={recipient}
          onChange={(e) => setRecipient(e.target.value as LetterRecipient)}
        >
          <option value="provider">The provider or billing office</option>
          <option value="insurer">My insurer</option>
        </select>

        <label htmlFor="letter-context">
          Anything you want to add? (optional)
        </label>
        <textarea
          id="letter-context"
          rows={3}
          value={context}
          onChange={(e) => setContext(e.target.value)}
          placeholder="For example: which charge you’re asking about, or dates."
        />

        <div className="actions">
          <button type="button" onClick={generate} disabled={busy}>
            {busy ? 'Drafting…' : 'Draft my letter'}
          </button>
        </div>
      </div>

      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}

      {(subject || body) && (
        <div className="card">
          <h2>Your draft</h2>
          <label htmlFor="draft-subject">Subject</label>
          <input
            id="draft-subject"
            value={subject}
            onChange={(e) => setSubject(e.target.value)}
          />
          <label htmlFor="draft-body">Letter</label>
          <textarea
            id="draft-body"
            rows={14}
            value={body}
            onChange={(e) => setBody(e.target.value)}
          />
          <div className="actions">
            <button type="button" onClick={copyToClipboard}>
              {copied ? 'Copied' : 'Copy'}
            </button>
            <button type="button" onClick={() => window.print()}>
              Print
            </button>
          </div>
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
