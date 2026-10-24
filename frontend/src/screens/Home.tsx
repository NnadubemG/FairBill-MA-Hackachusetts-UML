import { useState } from 'react';
import type { ExtractRequest } from '@contracts';
import { extract } from '../lib/api';
import {
  pdfSizeWarning,
  prepareDocument,
  type PreparedDocument,
} from '../lib/image';

interface HomeProps {
  onExtracted: (text: string, result: Awaited<ReturnType<typeof extract>>) => void;
  onGoToCompare: () => void;
}

export function Home({ onExtracted, onGoToCompare }: HomeProps) {
  const [text, setText] = useState('');
  const [document, setDocument] = useState<PreparedDocument | null>(null);
  const [documentName, setDocumentName] = useState('');
  const [busy, setBusy] = useState(false);
  const [warning, setWarning] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleFile(e: React.ChangeEvent<HTMLInputElement>) {
    setError(null);
    setWarning(null);
    setDocument(null);
    setDocumentName('');
    const file = e.target.files?.[0];
    if (!file) return;

    const pdfWarn = pdfSizeWarning(file);
    if (pdfWarn) {
      setWarning(pdfWarn);
      return;
    }

    try {
      setDocument(await prepareDocument(file));
      setDocumentName(file.name);
      setWarning(
        file.type.startsWith('image/')
          ? 'Image attached and resized before upload.'
          : 'PDF attached. Only attach bills you are comfortable submitting for this session.',
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not prepare that file.');
    }
  }

  async function handleSubmit() {
    setError(null);
    if (!text.trim() && !document) {
      setError('Please attach a bill or paste a few of its lines.');
      return;
    }
    setBusy(true);
    try {
      const req: ExtractRequest = {
        text: text.trim(),
        source_kind: 'unknown',
        ...(document ?? {}),
      };
      const result = await extract(req);
      onExtracted(text.trim(), result);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : 'Something went wrong reading the bill.',
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <section aria-labelledby="home-heading">
      <h1 id="home-heading">Make sense of a medical bill</h1>
      <p className="lede">
        Upload or paste a medical bill or Explanation of Benefits. We’ll pull out
        the line items, explain them in plain language, point out anything worth
        asking about, and help you draft a polite letter. You stay in control — the
        app informs and drafts; you decide and act.
      </p>

      <div className="card">
        <h2>Start with your bill</h2>
        <label htmlFor="bill-file">Upload a PDF or image (optional)</label>
        <input
          id="bill-file"
          type="file"
          accept="image/jpeg,image/png,image/webp,image/gif,application/pdf"
          onChange={handleFile}
        />
        {documentName && <p className="fineprint">Attached: {documentName}</p>}

        <label htmlFor="bill-text">Or paste the text from your bill</label>
        <textarea
          id="bill-text"
          rows={8}
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="Paste the lines from your bill or EOB here…"
        />

        {warning && <p className="notice" role="status">{warning}</p>}
        {error && <p className="error" role="alert">{error}</p>}

        <div className="actions">
          <button type="button" onClick={handleSubmit} disabled={busy}>
            {busy ? 'Reading…' : 'Read my bill'}
          </button>
          <button type="button" className="link" onClick={onGoToCompare}>
            Just look up a price
          </button>
        </div>
      </div>

      <p className="fineprint">
        Bill content is kept only for this session. We don’t use analytics.
      </p>
    </section>
  );
}
