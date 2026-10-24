// Frontend-only adapters for the team-owned backend interfaces.
// Uploaded strings are inert data and are sent only as request payloads.

async function responseJson(response) {
  let body;
  try { body = await response.json(); } catch { body = {}; }
  if (!response.ok || body.error) {
    throw new Error(body.error || `Request failed (${response.status})`);
  }
  return body;
}

/** POST raw bill bytes to Sam's agreed /extract adapter. */
export async function extractBill({ file, text }) {
  const body = file ? await file.arrayBuffer() : new TextEncoder().encode(text);
  const contentType = file?.type || "text/plain; charset=utf-8";
  const response = await fetch("/extract", {
    method: "POST",
    headers: { "content-type": contentType },
    body,
  });
  return responseJson(response);
}

/** POST confirmed canonical LineItem[] to ND's agreed /analyze adapter. */
export async function analyzeBill(lineItems) {
  const response = await fetch("/analyze", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ line_items: lineItems }),
  });
  return responseJson(response);
}

/** POST Sam's current LetterRequest shape to the agreed /letter adapter. */
export async function draftLetter({ lineItems, flags, letterType, patient }) {
  const response = await fetch("/letter", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      letter_type: letterType,
      patient,
      flags,
      line_items: lineItems,
    }),
  });
  return responseJson(response);
}
