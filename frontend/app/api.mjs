// Thin client for the FairBill API. Same origin by default; `?api=https://...` overrides
// for a split deployment. Nothing is cached or stored in the browser.

const params = new URLSearchParams(globalThis.location?.search || "");
export const API_BASE = (params.get("api") || "").replace(/\/$/, "");

export class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.status = status;
  }
}

async function request(path, { method = "GET", body, timeoutMs = 90000 } = {}) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);
  let res;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      method,
      headers: body ? { "Content-Type": "application/json" } : undefined,
      body: body ? JSON.stringify(body) : undefined,
      signal: ctrl.signal,
      cache: "no-store",
    });
  } catch (err) {
    throw new ApiError(
      err.name === "AbortError"
        ? "The request took too long. Please try again."
        : "Can't reach the FairBill server. Check your connection and try again.",
      0,
    );
  } finally {
    clearTimeout(timer);
  }
  let data = null;
  try {
    data = await res.json();
  } catch {
    data = null;
  }
  if (!res.ok) {
    throw new ApiError((data && data.error) || `Request failed (${res.status}).`, res.status);
  }
  return data;
}

export const api = {
  health: () => request("/health", { timeoutMs: 10000 }),
  procedures: () => request("/procedures"),
  compare: (code) => request(`/compare?code=${encodeURIComponent(code)}`),
  samples: () => request("/samples"),
  extract: (contentType, documentBase64) =>
    request("/extract", { method: "POST", body: { content_type: contentType, document_base64: documentBase64 } }),
  analyze: (lineItems) => request("/analyze", { method: "POST", body: { line_items: lineItems } }),
  letter: (payload) => request("/letter", { method: "POST", body: payload }),
};
