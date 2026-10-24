/**
 * API client. Talks to the same-origin /api/* endpoints. A `USE_FIXTURES` flag
 * lets the UI run against mock data before the backend is wired; set it to false
 * (or via VITE_USE_FIXTURES=false) to hit the real API.
 *
 * All request/response types come from the shared /contracts module.
 */
import type {
  AnalyzeRequest,
  AnalyzeResponse,
  CompareResponse,
  ExtractRequest,
  ExtractResponse,
  LetterRequest,
  LetterResponse,
  ProceduresResponse,
} from '@contracts';
import {
  fixtureAnalyze,
  fixtureExtract,
  fixtureLetter,
  fixtureProcedures,
} from './fixtures';

const USE_FIXTURES =
  (import.meta.env?.VITE_USE_FIXTURES ?? 'true') !== 'false';

async function postJson<TReq, TRes>(path: string, body: TReq): Promise<TRes> {
  const res = await fetch(path, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const err = await safeError(res);
    throw new ApiClientError(err, res.status);
  }
  return (await res.json()) as TRes;
}

async function getJson<TRes>(path: string): Promise<TRes> {
  const res = await fetch(path);
  if (!res.ok) {
    const err = await safeError(res);
    throw new ApiClientError(err, res.status);
  }
  return (await res.json()) as TRes;
}

async function safeError(res: Response): Promise<string> {
  try {
    const data = await res.json();
    return typeof data?.error === 'string' ? data.error : `HTTP ${res.status}`;
  } catch {
    return `HTTP ${res.status}`;
  }
}

export class ApiClientError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

const delay = (ms: number) => new Promise((r) => setTimeout(r, ms));

export async function extract(req: ExtractRequest): Promise<ExtractResponse> {
  if (USE_FIXTURES) {
    await delay(500);
    return fixtureExtract;
  }
  return postJson<ExtractRequest, ExtractResponse>('/api/extract', req);
}

export async function analyze(req: AnalyzeRequest): Promise<AnalyzeResponse> {
  if (USE_FIXTURES) {
    await delay(300);
    return fixtureAnalyze;
  }
  return postJson<AnalyzeRequest, AnalyzeResponse>('/api/analyze', req);
}

export async function letter(req: LetterRequest): Promise<LetterResponse> {
  if (USE_FIXTURES) {
    await delay(500);
    return fixtureLetter;
  }
  return postJson<LetterRequest, LetterResponse>('/api/letter', req);
}

export async function procedures(query?: string): Promise<ProceduresResponse> {
  if (USE_FIXTURES) {
    await delay(200);
    return fixtureProcedures;
  }
  const q = query ? `?query=${encodeURIComponent(query)}` : '';
  return getJson<ProceduresResponse>(`/api/procedures${q}`);
}

export async function compare(
  code: string,
  charged: number,
): Promise<CompareResponse> {
  // No fixture: compare is deterministic; in fixture mode we synthesize a result.
  if (USE_FIXTURES) {
    await delay(200);
    return {
      code,
      charged,
      medicare_reference: 9200,
      ma_price_range: { low: 11000, high: 24000, source: 'sample' },
      ratio_to_medicare: Math.round((charged / 9200) * 100) / 100,
      flags: [],
    };
  }
  return getJson<CompareResponse>(
    `/api/compare?code=${encodeURIComponent(code)}&charged=${charged}`,
  );
}
