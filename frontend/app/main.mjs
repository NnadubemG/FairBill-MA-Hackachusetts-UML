// FairBill MA single-page app. Vanilla ES modules, no build step, no storage.
// Flow: upload -> confirm lines -> results (flags from /core) -> letter draft.
// Everything lives in memory for this tab only and is gone on reload (nothing is stored).

import { api, ApiError } from "./api.mjs";
import {
  esc, moneyOrDash, money, parseAmount, rowToLineItem, validateRows, nextRowId,
  rowsFromExtraction, rowsFromLineItems, totalBilled, buildResultRows, summarize,
  flagText, flagSource, letterFlags, base64FromArrayBuffer, checkUpload,
  SEVERITY_LABEL, FLAG_TITLE, LETTER_TYPES,
} from "./logic.mjs";
import { mountCompare } from "../src/compare/compare.mjs";

const $view = document.getElementById("view");
const $status = document.getElementById("sr-status");

// ---------------------------------------------------------------- state (memory only)
const state = {
  health: null,
  procedures: null,      // [{code, plain_label, ...}]
  framingNote: "",
  samples: null,
  extraction: null,      // last /extract result
  rows: [],              // editable line rows
  analysis: null,        // last /analyze result
  letter: null,          // last /letter result
  letterType: null,
  patient: { name: "", account_number: "", hospital: "", date: "", notes: "" },
  busy: false,
};

function announce(msg) {
  $status.textContent = "";
  setTimeout(() => { $status.textContent = msg; }, 30);
}

// ---------------------------------------------------------------- router
const ROUTES = {
  "": renderHome,
  confirm: renderConfirm,
  results: renderResults,
  letter: renderLetter,
  compare: renderCompare,
  about: renderAbout,
};

function parseHash() {
  const raw = location.hash.replace(/^#\/?/, "");
  const [path, query = ""] = raw.split("?");
  return { path, query: new URLSearchParams(query) };
}

export function go(path) {
  location.hash = `#/${path}`;
}

function route() {
  const { path, query } = parseHash();
  const view = ROUTES[path] || renderHome;
  // Guard steps that need earlier data.
  if (path === "confirm" && !state.rows.length && !state.extraction) return go("");
  if ((path === "results" || path === "letter") && !state.analysis) return go(state.rows.length ? "confirm" : "");
  document.querySelectorAll("[data-nav]").forEach((a) => {
    const active = a.dataset.nav === (path === "compare" || path === "about" ? path : "bill");
    a.setAttribute("aria-current", active ? "page" : "false");
  });
  view(query);
  const h1 = $view.querySelector("h1");
  if (h1) { h1.setAttribute("tabindex", "-1"); h1.focus({ preventScroll: true }); }
  window.scrollTo(0, 0);
}

window.addEventListener("hashchange", route);

// ---------------------------------------------------------------- shared bits
function stepper(active) {
  const steps = ["Upload", "Confirm", "Review", "Letter"];
  return `<ol class="stepper" aria-label="Progress">${steps.map((s, i) => {
    const n = i + 1;
    const cls = n < active ? "done" : n === active ? "current" : "";
    return `<li class="${cls}" ${n === active ? 'aria-current="step"' : ""}><span class="num">${n < active ? "✓" : n}</span>${s}</li>`;
  }).join("")}</ol>`;
}

function errorBox(msg) {
  return `<div class="alert alert-error" role="alert"><strong>Something went wrong.</strong> ${esc(msg)}</div>`;
}

function spinner(label) {
  return `<span class="spinner" aria-hidden="true"></span><span>${esc(label)}</span>`;
}

function setBusy(btn, busy, label) {
  if (!btn) return;
  state.busy = busy;
  btn.disabled = busy;
  if (busy) {
    btn.dataset.label = btn.innerHTML;
    btn.innerHTML = spinner(label);
  } else if (btn.dataset.label) {
    btn.innerHTML = btn.dataset.label;
  }
}

async function ensureProcedures() {
  if (state.procedures) return state.procedures;
  try {
    const data = await api.procedures();
    state.procedures = data.procedures || [];
    state.framingNote = data.framing_note || "";
  } catch {
    state.procedures = [];
  }
  return state.procedures;
}

function procedureByCode(code) {
  const c = String(code || "").trim().toUpperCase();
  return (state.procedures || []).find((p) => p.code === c) || null;
}

// ---------------------------------------------------------------- home / upload
function renderHome() {
  const offline = state.health && state.health.model !== "live";
  $view.innerHTML = `
    <section class="hero">
      <p class="eyebrow"><span class="dot"></span> Free · No login · Nothing is stored</p>
      <h1>Understand your hospital bill, <span class="accent">line by line</span></h1>
      <p class="lede">Upload a Massachusetts hospital bill. We read the lines, compare each one to
        Medicare and real Massachusetts hospital prices, and point out what may be worth asking about.</p>
    </section>

    ${stepper(1)}

    <section class="card upload-card" aria-labelledby="upload-h">
      <h2 id="upload-h">Start with your bill</h2>
      <label class="dropzone" id="dropzone">
        <input type="file" id="file" accept="application/pdf,image/png,image/jpeg,image/webp,image/gif,text/plain,.txt" />
        <span class="dz-icon" aria-hidden="true">
          <svg width="40" height="40" viewBox="0 0 24 24" fill="none"><path d="M12 16V4m0 0-4 4m4-4 4 4M4 16v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>
        </span>
        <span class="dz-title" id="dz-title">Drop a PDF or photo of your bill here</span>
        <span class="dz-sub">or click to choose a file · PDF, PNG, JPG, TXT · up to 4 MB</span>
      </label>
      ${offline ? `<p class="hint">AI reading is off on this server. Text PDFs and .txt bills are still read directly;
        photos and scans need to be typed in.</p>` : ""}
      <div id="upload-error"></div>
      <div class="actions">
        <button class="btn btn-primary" id="read-btn" type="button" disabled>Read my bill</button>
        <button class="btn btn-ghost" id="manual-btn" type="button">Type my lines in instead</button>
      </div>

      <div class="divider"><span>or try it with a sample</span></div>
      <div class="sample-row">
        <label for="sample-select" class="sr-only">Sample bill</label>
        <select id="sample-select"><option value="">Loading samples…</option></select>
        <button class="btn btn-secondary" id="sample-btn" type="button" disabled>Use sample bill</button>
      </div>
      <p class="fineprint">Sample bills are fictional and made up for demos.</p>
    </section>

    <section class="how" aria-labelledby="how-h">
      <h2 id="how-h">How it works</h2>
      <div class="how-grid">
        ${howCard("1", "We read your bill", "An AI model turns your bill into a list of line items. It only reads; it doesn't judge anything.")}
        ${howCard("2", "You check the lines", "You confirm or fix every line before anything is compared. You're always in control.")}
        ${howCard("3", "Rules compare prices", "Plain, deterministic rules — not the AI — compare each line to public reference prices.")}
        ${howCard("4", "You get a letter draft", "Get an editable letter that asks the hospital or insurer your questions politely.")}
      </div>
      <p class="promise">Every price we show carries its source and year. If we don't have a reference figure, we say so — we never make one up.</p>
    </section>`;

  const $file = document.getElementById("file");
  const $read = document.getElementById("read-btn");
  const $dz = document.getElementById("dropzone");
  const $err = document.getElementById("upload-error");
  let chosen = null;

  function choose(file) {
    const problem = checkUpload(file);
    $err.innerHTML = problem ? errorBox(problem) : "";
    chosen = problem ? null : file;
    $read.disabled = !chosen;
    document.getElementById("dz-title").textContent = chosen ? `Ready: ${file.name}` : "Drop a PDF or photo of your bill here";
    $dz.classList.toggle("has-file", Boolean(chosen));
  }

  $file.addEventListener("change", () => choose($file.files[0]));
  ["dragenter", "dragover"].forEach((ev) => $dz.addEventListener(ev, (e) => { e.preventDefault(); $dz.classList.add("drag"); }));
  ["dragleave", "drop"].forEach((ev) => $dz.addEventListener(ev, (e) => { e.preventDefault(); $dz.classList.remove("drag"); }));
  $dz.addEventListener("drop", (e) => choose(e.dataTransfer.files[0]));

  $read.addEventListener("click", async () => {
    if (!chosen || state.busy) return;
    setBusy($read, true, "Reading your bill…");
    announce("Reading your bill. This can take up to a minute.");
    try {
      const b64 = base64FromArrayBuffer(await chosen.arrayBuffer());
      const type = chosen.type || (/\.txt$/i.test(chosen.name) ? "text/plain" : "");
      const result = await api.extract(type, b64);
      state.extraction = result;
      state.rows = rowsFromExtraction(result);
      if (!state.rows.length) state.rows = [blankRow("1")]; // always give a row to type into
      if (result.metadata?.hospital_name && !state.patient.hospital) state.patient.hospital = result.metadata.hospital_name;
      state.analysis = null;
      state.letter = null;
      go("confirm");
    } catch (e) {
      $err.innerHTML = errorBox(e instanceof ApiError ? e.message : "We couldn't read that file.");
    } finally {
      setBusy($read, false);
    }
  });

  document.getElementById("manual-btn").addEventListener("click", () => {
    state.extraction = { line_items: [], warnings: [], metadata: {}, line_confidence: [] };
    state.rows = [blankRow("1")];
    state.analysis = null;
    go("confirm");
  });

  loadSamples();
}

function howCard(n, title, body) {
  return `<div class="how-card"><span class="how-n">${n}</span><h3>${esc(title)}</h3><p>${esc(body)}</p></div>`;
}

async function loadSamples() {
  const $sel = document.getElementById("sample-select");
  const $btn = document.getElementById("sample-btn");
  if (!$sel) return;
  try {
    if (!state.samples) state.samples = (await api.samples()).samples || [];
    if (!state.samples.length) throw new Error("none");
    $sel.innerHTML = state.samples
      .map((s) => `<option value="${esc(s.id)}">${esc(s.label)}</option>`).join("");
    $btn.disabled = false;
    $btn.onclick = () => {
      const s = state.samples.find((x) => x.id === $sel.value);
      if (!s) return;
      state.extraction = { line_items: s.line_items, warnings: [], metadata: s.metadata || {}, line_confidence: [] };
      state.rows = rowsFromLineItems(s.line_items);
      if (s.metadata?.hospital_name) state.patient.hospital = s.metadata.hospital_name;
      state.analysis = null;
      state.letter = null;
      go("confirm");
    };
  } catch {
    $sel.innerHTML = `<option value="">No samples available</option>`;
  }
}

function blankRow(id) {
  return { id, description: "", code: "", code_system: null, quantity: "1", unit: null,
    date_of_service: "", billed_amount: "", raw_description: null, needs_confirmation: false };
}

// ---------------------------------------------------------------- confirm
function renderConfirm() {
  const ex = state.extraction || {};
  const warnings = ex.warnings || [];
  const meta = ex.metadata || {};
  const needs = state.rows.filter((r) => r.needs_confirmation).length;

  $view.innerHTML = `
    ${stepper(2)}
    <header class="page-head">
      <h1>Check your bill's lines</h1>
      <p class="lede">Make sure each line matches your bill. Fix anything that looks off, add missing lines,
        or remove extras. Nothing is compared until you say so.</p>
    </header>

    ${warnings.length ? `<div class="alert alert-info" role="status"><ul>${warnings.map((w) => `<li>${esc(w)}</li>`).join("")}</ul></div>` : ""}
    ${needs ? `<div class="alert alert-warn" role="status"><strong>${needs} line${needs > 1 ? "s" : ""} need a quick look.</strong>
      We weren't fully sure we read ${needs > 1 ? "them" : "it"} correctly — they're highlighted below.</div>` : ""}

    ${(meta.hospital_name || meta.statement_date || meta.total != null) ? `
      <div class="meta-strip">
        ${meta.hospital_name ? `<div><span>Hospital</span><strong>${esc(meta.hospital_name)}</strong></div>` : ""}
        ${meta.statement_date ? `<div><span>Statement date</span><strong>${esc(meta.statement_date)}</strong></div>` : ""}
        ${meta.total != null ? `<div><span>Bill total</span><strong>${esc(moneyOrDash(meta.total))}</strong></div>` : ""}
      </div>` : ""}

    <section class="card table-card">
      <div class="table-scroll">
        <table class="edit-table">
          <caption class="sr-only">Line items from your bill</caption>
          <thead><tr>
            <th scope="col" class="c-desc">Description</th>
            <th scope="col" class="c-code">Code <span class="th-hint">(CPT/HCPCS)</span></th>
            <th scope="col" class="c-qty">Qty</th>
            <th scope="col" class="c-date">Date</th>
            <th scope="col" class="c-amt">Billed</th>
            <th scope="col" class="c-x"><span class="sr-only">Remove</span></th>
          </tr></thead>
          <tbody id="rows">${state.rows.map(rowHtml).join("")}</tbody>
          <tfoot><tr>
            <td colspan="4"><button class="btn btn-ghost btn-sm" id="add-row" type="button">+ Add a line</button></td>
            <td class="total-cell"><span>Total</span><strong id="total">${esc(moneyOrDash(totalBilled(state.rows)))}</strong></td>
            <td></td>
          </tr></tfoot>
        </table>
      </div>
    </section>

    <div id="confirm-errors"></div>
    <div class="actions actions-split">
      <a class="btn btn-ghost" href="#/">← Start over</a>
      <button class="btn btn-primary btn-lg" id="analyze-btn" type="button">Check my bill →</button>
    </div>`;

  const $rows = document.getElementById("rows");

  $rows.addEventListener("input", (e) => {
    const el = e.target;
    const row = state.rows.find((r) => r.id === el.dataset.row);
    if (!row) return;
    row[el.dataset.field] = el.value;
    if (el.dataset.field === "code") row.code_system = null; // re-derive from the new code
    el.closest("tr")?.classList.remove("has-error");
    el.removeAttribute("aria-invalid");
    if (el.dataset.field === "billed_amount") {
      document.getElementById("total").textContent = moneyOrDash(totalBilled(state.rows));
    }
  });

  $rows.addEventListener("click", (e) => {
    const btn = e.target.closest("[data-remove]");
    if (btn) {
      state.rows = state.rows.filter((r) => r.id !== btn.dataset.remove);
      renderConfirm();
      announce("Line removed.");
      return;
    }
    const ok = e.target.closest("[data-confirm]");
    if (ok) {
      const row = state.rows.find((r) => r.id === ok.dataset.confirm);
      if (row) row.needs_confirmation = false;
      renderConfirm();
    }
  });

  document.getElementById("add-row").addEventListener("click", () => {
    const id = nextRowId(state.rows);
    state.rows.push(blankRow(id));
    renderConfirm();
    document.querySelector(`[data-row="${id}"][data-field="description"]`)?.focus();
  });

  document.getElementById("analyze-btn").addEventListener("click", runAnalyze);
}

function rowHtml(r) {
  const flag = r.needs_confirmation;
  const inp = (field, type, extra = "") =>
    `<input type="${type}" data-row="${esc(r.id)}" data-field="${field}" value="${esc(r[field] ?? "")}" ${extra} />`;
  return `<tr class="${flag ? "needs-check" : ""}" data-tr="${esc(r.id)}">
    <td class="c-desc">
      <label class="sr-only" for="d-${esc(r.id)}">Description, line ${esc(r.id)}</label>
      ${inp("description", "text", `id="d-${esc(r.id)}" placeholder="e.g. Office visit" maxlength="256"`)}
      ${r.raw_description && r.raw_description !== r.description ? `<span class="raw">On bill: ${esc(r.raw_description)}</span>` : ""}
      ${flag ? `<span class="check-pill">Please check <button type="button" class="link" data-confirm="${esc(r.id)}">Looks right</button></span>` : ""}
    </td>
    <td class="c-code"><label class="sr-only" for="c-${esc(r.id)}">Code, line ${esc(r.id)}</label>
      ${inp("code", "text", `id="c-${esc(r.id)}" placeholder="99213" maxlength="16" autocomplete="off" spellcheck="false"`)}</td>
    <td class="c-qty"><label class="sr-only" for="q-${esc(r.id)}">Quantity, line ${esc(r.id)}</label>
      ${inp("quantity", "text", `id="q-${esc(r.id)}" inputmode="decimal" placeholder="1"`)}</td>
    <td class="c-date"><label class="sr-only" for="t-${esc(r.id)}">Date of service, line ${esc(r.id)}</label>
      ${inp("date_of_service", "date", `id="t-${esc(r.id)}"`)}</td>
    <td class="c-amt"><label class="sr-only" for="a-${esc(r.id)}">Billed amount, line ${esc(r.id)}</label>
      <div class="money-in"><span aria-hidden="true">$</span>${inp("billed_amount", "text", `id="a-${esc(r.id)}" inputmode="decimal" placeholder="0.00"`)}</div></td>
    <td class="c-x"><button type="button" class="icon-btn" data-remove="${esc(r.id)}" aria-label="Remove line ${esc(r.id)}">✕</button></td>
  </tr>`;
}

async function runAnalyze() {
  const $btn = document.getElementById("analyze-btn");
  const $err = document.getElementById("confirm-errors");
  const errors = validateRows(state.rows);
  document.querySelectorAll("[aria-invalid]").forEach((el) => el.removeAttribute("aria-invalid"));
  if (errors.length) {
    for (const er of errors) {
      if (!er.rowId) continue;
      const el = document.querySelector(`[data-row="${er.rowId}"][data-field="${er.field}"]`);
      el?.setAttribute("aria-invalid", "true");
      el?.closest("tr")?.classList.add("has-error");
    }
    const unique = [...new Set(errors.map((e) => e.message))];
    $err.innerHTML = `<div class="alert alert-error" role="alert"><strong>A few lines need fixing:</strong>
      <ul>${unique.map((m) => `<li>${esc(m)}</li>`).join("")}</ul></div>`;
    document.querySelector("[aria-invalid]")?.focus();
    return;
  }
  $err.innerHTML = "";
  setBusy($btn, true, "Comparing prices…");
  announce("Comparing your lines to reference prices.");
  try {
    state.analysis = await api.analyze(state.rows.map(rowToLineItem));
    state.letter = null;
    await ensureProcedures();
    go("results");
  } catch (e) {
    $err.innerHTML = errorBox(e instanceof ApiError ? e.message : "We couldn't check your bill.");
  } finally {
    setBusy($btn, false);
  }
}

// ---------------------------------------------------------------- results
function renderResults() {
  const a = state.analysis;
  const s = summarize(a);
  const rows = buildResultRows(a);

  const headline = s.questionCount
    ? `We found <strong>${s.questionCount}</strong> thing${s.questionCount > 1 ? "s" : ""} that may be worth asking about`
    : `Nothing on your bill stood out against our reference data`;

  $view.innerHTML = `
    ${stepper(3)}
    <header class="page-head">
      <h1>Your bill, reviewed</h1>
      <p class="lede">${headline}${s.questionCount ? ` across ${s.linesWithQuestions} line${s.linesWithQuestions > 1 ? "s" : ""}.` : "."}
        These are questions, not conclusions — a hospital may have a good reason for a charge.</p>
    </header>

    <div class="summary-grid">
      ${tile("Lines checked", String(s.lineCount))}
      ${tile("Total billed", moneyOrDash(s.total))}
      ${tile("Worth asking about", String(s.questionCount), s.questionCount ? "accent" : "good")}
      ${tile("No reference price", String(s.linesWithoutReference), "muted")}
    </div>

    ${state.framingNote ? `<p class="framing-note">${esc(state.framingNote)}</p>` : ""}

    <section class="result-list" aria-label="Line by line">
      ${rows.map(resultCard).join("")}
    </section>

    <section class="card cta-card">
      <div>
        <h2>Ready to ask your questions?</h2>
        <p>Get an editable letter you can send to the hospital's billing office or your insurer.</p>
      </div>
      <div class="actions">
        <a class="btn btn-ghost" href="#/confirm">← Edit lines</a>
        <a class="btn btn-primary btn-lg" href="#/letter">Draft a letter →</a>
      </div>
    </section>`;
}

function tile(label, value, tone = "") {
  return `<div class="tile ${tone}"><span class="tile-k">${esc(label)}</span><span class="tile-v">${esc(value)}</span></div>`;
}

function resultCard({ item, flags, reference }) {
  const askable = flags.filter((f) => f.flag_type !== "no_reference_found");
  const noRef = flags.find((f) => f.flag_type === "no_reference_found");
  const worst = askable[0]?.severity;
  const proc = procedureByCode(item.code);
  const qty = item.quantity && item.quantity !== 1 ? ` · qty ${esc(item.quantity)}` : "";

  return `<article class="result-card ${worst ? `sev-${worst}` : noRef ? "sev-none" : "sev-clean"}">
    <header class="rc-head">
      <div>
        <h3>${esc(item.description)}</h3>
        <p class="rc-sub">
          ${item.code ? `<span class="chip">${esc(item.code_system || "Code")} ${esc(item.code)}</span>` : `<span class="chip chip-muted">No code</span>`}
          ${item.date_of_service ? `<span>${esc(item.date_of_service)}</span>` : ""}${qty}
        </p>
      </div>
      <div class="rc-amt"><span>Billed</span><strong>${esc(moneyOrDash(item.billed_amount))}</strong></div>
    </header>

    ${reference ? refStrip(reference) : ""}

    ${askable.length ? `<ul class="flag-list">${askable.map(flagItem).join("")}</ul>` : ""}
    ${!askable.length && !noRef ? `<p class="clean-note"><span aria-hidden="true">✓</span> Nothing stood out for this line.</p>` : ""}
    ${noRef ? `<p class="noref-note">${esc(flagText(noRef))}</p>` : ""}

    ${proc ? `<a class="rc-link" href="#/compare?code=${encodeURIComponent(proc.code)}">See what Massachusetts hospitals charge for this →</a>` : ""}
  </article>`;
}

function refStrip(r) {
  const parts = [];
  if (r.medicare_price != null) parts.push(`<div><span>Medicare reference</span><strong>${esc(money(r.medicare_price))}</strong></div>`);
  if (r.ma_range_low != null || r.ma_range_high != null) {
    const lo = moneyOrDash(r.ma_range_low);
    const hi = moneyOrDash(r.ma_range_high);
    parts.push(`<div><span>Massachusetts range</span><strong>${esc(lo === hi ? lo : `${lo} – ${hi}`)}</strong></div>`);
  }
  if (!parts.length) return "";
  return `<div class="ref-strip">${parts.join("")}<p class="src">Source: ${esc(r.data_source)}${r.data_year ? `, ${esc(r.data_year)}` : ""}</p></div>`;
}

function flagItem(f) {
  const src = flagSource(f);
  return `<li class="flag flag-${esc(f.severity)}">
    <div class="flag-top">
      <span class="sev-badge sev-${esc(f.severity)}">${esc(SEVERITY_LABEL[f.severity] || f.severity)}</span>
      <strong>${esc(FLAG_TITLE[f.flag_type] || f.flag_type)}</strong>
    </div>
    <p>${esc(flagText(f))}</p>
    <details><summary>What this is based on</summary>
      <p>${esc(f.basis)}</p>${src ? `<p class="src">Source: ${esc(src)}</p>` : ""}
    </details>
  </li>`;
}

// ---------------------------------------------------------------- letter
function renderLetter() {
  const a = state.analysis;
  const flags = letterFlags(a.flags);
  if (!state.letterType) state.letterType = flags.length ? "coding_review" : "itemized_bill";
  if (!state.patient.date) state.patient.date = new Date().toISOString().slice(0, 10);
  const p = state.patient;
  const L = state.letter;

  $view.innerHTML = `
    ${stepper(4)}
    <header class="page-head">
      <h1>Draft your letter</h1>
      <p class="lede">Pick what you want to ask for. You'll get a polite, editable draft — change anything you like before you send it.</p>
    </header>

    <div class="letter-grid">
      <form class="card letter-form" id="letter-form" novalidate>
        <fieldset>
          <legend>What would you like to ask for?</legend>
          <div class="type-cards">
            ${LETTER_TYPES.map((t) => `
              <label class="type-card ${state.letterType === t.id ? "selected" : ""}">
                <input type="radio" name="ltype" value="${t.id}" ${state.letterType === t.id ? "checked" : ""} />
                <span class="tc-title">${esc(t.title)}</span>
                <span class="tc-blurb">${esc(t.blurb)}${t.id === "coding_review" ? ` ${flags.length ? `(${flags.length} item${flags.length > 1 ? "s" : ""} included)` : "(no flagged items)"}` : ""}</span>
              </label>`).join("")}
          </div>
        </fieldset>

        <fieldset>
          <legend>Your details <span class="legend-hint">(optional — used only in this letter, never stored)</span></legend>
          <div class="form-grid">
            ${field("name", "Your name", p.name, "text", 'autocomplete="name"')}
            ${field("account_number", "Account number", p.account_number, "text", 'autocomplete="off"')}
            ${field("hospital", "Hospital or insurer", p.hospital, "text", "")}
            ${field("date", "Date", p.date, "date", "")}
          </div>
          <label class="field">
            <span>Anything else to add?</span>
            <textarea name="notes" rows="3" maxlength="1000" placeholder="e.g. My visit was on March 3.">${esc(p.notes)}</textarea>
          </label>
        </fieldset>
        <div id="letter-error"></div>
        <button class="btn btn-primary btn-lg btn-block" id="gen-btn" type="submit">${L ? "Regenerate draft" : "Create my letter"}</button>
      </form>

      <section class="card letter-out" aria-labelledby="draft-h" aria-live="polite">
        <h2 id="draft-h">Your draft</h2>
        ${L ? letterOutput(L) : `<div class="empty-draft"><span aria-hidden="true">✉️</span><p>Your letter will show up here. You can edit it, copy it, or download it.</p></div>`}
      </section>
    </div>

    <div class="actions actions-split">
      <a class="btn btn-ghost" href="#/results">← Back to results</a>
      <a class="btn btn-ghost" href="#/" id="restart">Check another bill</a>
    </div>`;

  const $form = document.getElementById("letter-form");
  $form.addEventListener("change", (e) => {
    if (e.target.name === "ltype") {
      state.letterType = e.target.value;
      $form.querySelectorAll(".type-card").forEach((c) => c.classList.toggle("selected", c.querySelector("input").checked));
    }
  });
  $form.addEventListener("input", (e) => {
    if (e.target.name in state.patient) state.patient[e.target.name] = e.target.value;
  });
  $form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const $btn = document.getElementById("gen-btn");
    setBusy($btn, true, "Writing your letter…");
    announce("Writing your letter.");
    try {
      state.letter = await api.letter({
        letter_type: state.letterType,
        patient: { ...state.patient },
        flags: state.letterType === "coding_review" ? flags : [],
        line_items: a.line_items,
      });
      state.busy = false;
      renderLetter();
      document.getElementById("draft-body")?.focus();
      announce("Your letter draft is ready.");
    } catch (err) {
      document.getElementById("letter-error").innerHTML = errorBox(err instanceof ApiError ? err.message : "We couldn't create the letter.");
      setBusy($btn, false);
    }
  });
  document.getElementById("restart").addEventListener("click", () => resetBill());
  wireLetterOutput();
}

function field(name, label, value, type, extra) {
  return `<label class="field"><span>${esc(label)}</span><input type="${type}" name="${name}" value="${esc(value)}" maxlength="200" ${extra} /></label>`;
}

function letterOutput(L) {
  const d = L.draft || {};
  return `
    ${(L.warnings || []).length ? `<div class="alert alert-info" role="status">${L.warnings.map((w) => esc(w)).join("<br>")}</div>` : ""}
    <label class="field"><span>Subject</span><input id="draft-subject" type="text" value="${esc(d.subject)}" /></label>
    <label class="field"><span>Letter</span><textarea id="draft-body" rows="18">${esc(d.body)}</textarea></label>
    <div class="actions">
      <button class="btn btn-primary" id="copy-btn" type="button">Copy letter</button>
      <button class="btn btn-secondary" id="dl-btn" type="button">Download .txt</button>
      <button class="btn btn-ghost" id="print-btn" type="button">Print</button>
    </div>
    <p class="fineprint">Tip: letters that ask clear questions tend to get clear answers. Keep a copy of what you send.</p>`;
}

function currentLetterText() {
  const subj = document.getElementById("draft-subject")?.value || "";
  const body = document.getElementById("draft-body")?.value || "";
  return `Subject: ${subj}\n\n${body}\n`;
}

function wireLetterOutput() {
  document.getElementById("copy-btn")?.addEventListener("click", async (e) => {
    try {
      await navigator.clipboard.writeText(currentLetterText());
      e.target.textContent = "Copied ✓";
      announce("Letter copied to clipboard.");
      setTimeout(() => { e.target.textContent = "Copy letter"; }, 1800);
    } catch {
      document.getElementById("draft-body")?.select();
      announce("Select the text and copy it with Ctrl+C.");
    }
  });
  document.getElementById("dl-btn")?.addEventListener("click", () => {
    const blob = new Blob([currentLetterText()], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = Object.assign(document.createElement("a"), { href: url, download: "fairbill-letter.txt" });
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  });
  document.getElementById("print-btn")?.addEventListener("click", () => {
    const w = window.open("", "_blank", "noopener,width=720,height=900");
    if (!w) return;
    w.document.write(`<pre style="font:14px/1.6 Georgia,serif;white-space:pre-wrap;padding:40px">${esc(currentLetterText())}</pre>`);
    w.document.close();
    w.focus();
    w.print();
  });
}

function resetBill() {
  Object.assign(state, { extraction: null, rows: [], analysis: null, letter: null, letterType: null });
  state.patient = { name: "", account_number: "", hospital: "", date: "", notes: "" };
}

// ---------------------------------------------------------------- compare
async function renderCompare(query) {
  $view.innerHTML = `
    <header class="page-head">
      <h1>Compare hospital prices</h1>
      <p class="lede">See Medicare benchmarks and what Massachusetts hospitals list for common procedures,
        straight from their public price files.</p>
    </header>
    <div class="card search-panel">
      <label for="proc" class="field-k">Procedure</label>
      <div class="search-row">
        <select id="proc"><option>Loading…</option></select>
        <button class="btn btn-primary" id="cmp-btn" type="button">Compare prices</button>
      </div>
    </div>
    <div id="cmp-out" aria-live="polite"></div>`;

  const procs = await ensureProcedures();
  const $sel = document.getElementById("proc");
  const $out = document.getElementById("cmp-out");
  if (!$sel) return; // navigated away while loading
  if (!procs.length) {
    $sel.innerHTML = `<option value="">No procedures loaded</option>`;
    $out.innerHTML = errorBox("No price data is loaded on this server yet.");
    return;
  }
  const byCategory = {};
  for (const p of procs) (byCategory[p.category || "other"] ||= []).push(p);
  const catLabel = { office_visit: "Office visits", er_visit: "Emergency room", lab: "Lab tests",
    imaging: "Imaging", procedure: "Procedures", diagnostic: "Diagnostics", therapy: "Therapy" };
  $sel.innerHTML = Object.entries(byCategory).map(([cat, list]) =>
    `<optgroup label="${esc(catLabel[cat] || cat)}">${list.map((p) =>
      `<option value="${esc(p.code)}">${esc(p.plain_label)} (${esc(p.code)})</option>`).join("")}</optgroup>`).join("");

  const want = query.get("code");
  if (want && procs.some((p) => p.code === want)) $sel.value = want;

  const run = async () => {
    const code = $sel.value;
    if (!code) return;
    history.replaceState(null, "", `#/compare?code=${encodeURIComponent(code)}`);
    $out.innerHTML = `<div class="skeleton"></div><div class="skeleton short"></div>`;
    try {
      const data = await api.compare(code);
      renderCompareResult($out, data);
    } catch (e) {
      $out.innerHTML = errorBox(e.message);
    }
  };
  document.getElementById("cmp-btn").addEventListener("click", run);
  $sel.addEventListener("change", run);
  if (want) run();
}

const PAYER = {
  commercial: ["Commercial (negotiated)", "#2563eb"],
  medicare_advantage: ["Medicare Advantage", "#0891b2"],
  medicaid_managed: ["Medicaid managed", "#0f9d6b"],
  cash: ["Cash price", "#7c3aed"],
  gross: ["Gross charge", "#c2410c"],
};

function renderCompareResult($out, d) {
  if (!d.found) {
    $out.innerHTML = `<div class="card empty-state"><p>${esc(d.note || "No data for this code.")}</p></div>`;
    return;
  }
  const sw = d.statewide || {};
  const ref = d.reference || {};
  $out.innerHTML = `
    <section class="card">
      <div class="proc-head">
        <h2>${esc(d.plain_label || d.code)}</h2>
        <p class="rc-sub"><span class="chip">${esc(d.code_system || "")} ${esc(d.code)}</span>
          <span class="chip">Data year ${esc((d.data_years || []).join(", ") || "—")}</span>
          <span class="chip">${(d.hospitals || []).length} hospital${(d.hospitals || []).length === 1 ? "" : "s"}</span></p>
      </div>
      <div class="summary-grid">
        ${tile("Medicare reference", moneyOrDash(ref.medicare_price), ref.medicare_price == null ? "muted" : "")}
        ${tile("Statewide commercial median", moneyOrDash(sw.median))}
        ${tile("Lowest gross charge", moneyOrDash(sw.ma_range_low))}
        ${tile("Highest gross charge", moneyOrDash(sw.ma_range_high))}
      </div>
      ${ref.medicare_price == null ? `<p class="hint">No Medicare reference is loaded for this code yet, so we don't show one.</p>` : ""}
      <div id="chart" class="chart-wrap"></div>
    </section>
    ${(d.hospitals || []).map(hospitalCard).join("")}
    <p class="framing-note">${esc(d.framing_note || "")}</p>`;
  try {
    mountCompare(document.getElementById("chart"), d);
  } catch {
    document.getElementById("chart").remove();
  }
}

function hospitalCard(h) {
  const rows = Object.keys(PAYER).filter((g) => h.price_stats[g]).map((g) => {
    const ps = h.price_stats[g];
    const [label, color] = PAYER[g];
    const sw = `<span class="swatch" style="background:${color}"></span>`;
    if (g === "cash" || g === "gross") {
      return `<tr><th scope="row">${sw}${label}</th><td class="num" colspan="3">${esc(moneyOrDash(g === "cash" ? ps.cash_price : ps.gross_charge))}</td></tr>`;
    }
    return `<tr><th scope="row">${sw}${label}</th><td class="num">${esc(moneyOrDash(ps.min_rate))}</td>
      <td class="num">${esc(moneyOrDash(ps.median_rate))}</td><td class="num">${esc(moneyOrDash(ps.max_rate))}</td></tr>`;
  }).join("");
  const src = Object.values(h.price_stats)[0];
  const initials = (h.name || h.hospital_id).split(/\s+/).filter((w) => /^[A-Z]/.test(w)).slice(0, 2).map((w) => w[0]).join("");
  return `<section class="card hosp-card">
    <header class="hosp-head">
      <span class="avatar" aria-hidden="true">${esc(initials || "H")}</span>
      <div><h3>${esc(h.name || h.hospital_id)}</h3><p class="rc-sub">${esc([h.city, h.type].filter(Boolean).join(" · "))}</p></div>
    </header>
    <div class="table-scroll"><table class="price-table">
      <caption class="sr-only">Prices at ${esc(h.name)}</caption>
      <thead><tr><th scope="col">Payer group</th><th scope="col" class="num">Low</th><th scope="col" class="num">Median</th><th scope="col" class="num">High</th></tr></thead>
      <tbody>${rows || `<tr><td colspan="4">No price data for this hospital.</td></tr>`}</tbody>
    </table></div>
    ${h.missing_note ? `<p class="hint">${esc(h.missing_note)}</p>` : ""}
    ${src ? `<p class="src">Source: ${esc(src.data_source)}, ${esc(src.data_year)}</p>` : ""}
  </section>`;
}

// ---------------------------------------------------------------- about
function renderAbout() {
  $view.innerHTML = `
    <header class="page-head"><h1>About FairBill MA</h1>
      <p class="lede">A free tool for adults in Massachusetts trying to understand their own hospital bill.</p></header>
    <section class="card prose">
      <h2>What we do</h2>
      <ul>
        <li>Read your bill into a list of lines (an AI model does the reading — nothing more).</li>
        <li>Let you confirm every line before anything is compared.</li>
        <li>Compare each line to Medicare reference prices and real Massachusetts hospital prices using plain, deterministic rules.</li>
        <li>Point out what may be worth asking about, always with the reason and the data behind it.</li>
        <li>Draft a polite, editable letter you can send.</li>
      </ul>
      <h2>What we don't do</h2>
      <ul>
        <li>We don't give legal or medical advice.</li>
        <li>We don't store your bill, your lines, or your letter. Close the tab and it's gone.</li>
        <li>We never make up a price. If we don't have a reference figure, we tell you.</li>
      </ul>
      <h2>Where the prices come from</h2>
      <p>Hospital prices come from each hospital's own public price-transparency file (required by federal law, 45 CFR 180).
        Every figure on the site shows its source and year. What you actually pay depends on your plan and your care.</p>
    </section>`;
}

// ---------------------------------------------------------------- boot
async function boot() {
  try {
    state.health = await api.health();
    const pill = document.getElementById("status-pill");
    if (pill) {
      pill.hidden = false;
      pill.textContent = state.health.model === "live" ? "Bill reading on" : "Demo mode";
      pill.title = state.health.model === "live"
        ? "Bills are read automatically."
        : "Automatic bill reading is off on this server. You can type lines in or use a sample.";
    }
  } catch {
    state.health = null;
  }
  route();
}

boot();
