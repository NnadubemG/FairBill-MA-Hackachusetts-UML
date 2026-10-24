// Thin client for the compare API. Browser fetch; no dependency.
// baseUrl defaults to the local compare server.

const DEFAULT_BASE = "http://127.0.0.1:8000";

export async function fetchProcedures(baseUrl = DEFAULT_BASE) {
  const res = await fetch(`${baseUrl}/procedures`);
  if (!res.ok) throw new Error(`procedures: ${res.status}`);
  return res.json();
}

export async function fetchCompare(code, baseUrl = DEFAULT_BASE) {
  const res = await fetch(`${baseUrl}/compare?code=${encodeURIComponent(code)}`);
  if (!res.ok) throw new Error(`compare: ${res.status}`);
  return res.json();
}
