import { analyzeBill, draftLetter, extractBill } from "./api.mjs";
import { prepareUpload, validateUpload } from "./image.mjs";
import { resources } from "./resources.mjs";
import { fetchCompare } from "./compare/api.mjs";
import { mountCompare } from "./compare/compare.mjs";

const main = document.querySelector("#main");
const state = { screen: "home", file: null, lineItems: [], confidence: [], analysis: null };

const sample = {
  line_items: [
    { id: "line-1", code: "99213", code_system: "CPT", description: "Office visit", quantity: 1, unit: "visit", billed_amount: 240 },
    { id: "line-2", code: "80053", code_system: "CPT", description: "Comprehensive metabolic panel", quantity: 1, unit: "panel", billed_amount: 85 },
  ],
  line_confidence: [
    { line_item_id: "line-1", confidence: "high", needs_confirmation: false },
    { line_item_id: "line-2", confidence: "low", needs_confirmation: true },
  ],
  warnings: [],
};

document.querySelector("#home-button").addEventListener("click", () => show("home"));
show("home");

function show(screen) {
  state.screen = screen;
  main.replaceChildren();
  ({ home: renderHome, confirm: renderConfirm, results: renderResults, letter: renderLetter, compare: renderCompare }[screen] || renderHome)();
  main.focus();
}

function notice(text, kind = "notice") {
  const p = document.createElement("p");
  p.className = kind;
  p.setAttribute("role", kind === "error" ? "alert" : "status");
  p.textContent = text;
  return p;
}

function button(label, action, secondary = false) {
  const b = document.createElement("button");
  b.type = "button";
  b.textContent = label;
  if (secondary) b.className = "secondary";
  b.addEventListener("click", action);
  return b;
}

function generalInfo() {
  const aside = document.createElement("aside");
  aside.className = "general-info";
  aside.textContent = "General information only. Confirm important details with your provider, insurer, or an official Massachusetts source before acting.";
  return aside;
}

function renderHome() {
  main.innerHTML = `
    <section aria-labelledby="home-title">
      <h1 id="home-title">Make sense of a medical bill</h1>
      <p class="lede">Attach a bill or paste its text. You can check every extracted field before continuing.</p>
      <div class="card">
        <h2>Start with your bill</h2>
        <label for="bill-file">PDF or image</label>
        <input id="bill-file" type="file" accept="application/pdf,image/jpeg,image/png,image/webp,image/gif">
        <label for="bill-text">Or paste bill text</label>
        <textarea id="bill-text" rows="8" placeholder="Paste bill or Explanation of Benefits text here"></textarea>
        <div id="home-message"></div>
        <div class="actions" id="home-actions"></div>
      </div>
      <p class="fineprint">Bill content stays in memory for this browser session. No analytics are included.</p>
    </section>`;

  const fileInput = main.querySelector("#bill-file");
  const textInput = main.querySelector("#bill-text");
  const message = main.querySelector("#home-message");
  const actions = main.querySelector("#home-actions");

  fileInput.addEventListener("change", async () => {
    message.replaceChildren();
    const chosen = fileInput.files[0];
    if (!chosen) { state.file = null; return; }
    const problem = validateUpload(chosen);
    if (problem) { state.file = null; message.append(notice(problem, "error")); return; }
    try {
      state.file = await prepareUpload(chosen);
      message.append(notice(state.file.type.startsWith("image/") ? "Image attached and resized." : "PDF attached."));
    } catch (error) {
      state.file = null;
      message.append(notice(error.message || "Could not prepare that file.", "error"));
    }
  });

  actions.append(
    button("Read my bill", async (event) => {
      const trigger = event.currentTarget;
      const text = textInput.value.trim();
      if (!state.file && !text) { message.replaceChildren(notice("Attach a bill or paste some text first.", "error")); return; }
      trigger.disabled = true;
      trigger.textContent = "Reading…";
      message.replaceChildren();
      try {
        const result = await extractBill({ file: state.file, text });
        state.lineItems = result.line_items || [];
        state.confidence = result.line_confidence || [];
        if (!state.lineItems.length) throw new Error("No line items were found. Try clearer text or another file.");
        show("confirm");
      } catch (error) {
        message.append(notice(`${error.message || "Extraction is not available."} You can use the example bill to review the interface.`, "error"));
        trigger.disabled = false;
        trigger.textContent = "Read my bill";
      }
    }),
    button("Use example bill", () => {
      state.lineItems = structuredClone(sample.line_items);
      state.confidence = structuredClone(sample.line_confidence);
      show("confirm");
    }, true),
    button("Compare a procedure", () => show("compare"), true),
  );
}

function renderConfirm() {
  const section = document.createElement("section");
  section.innerHTML = `<h1>Check the extracted lines</h1><p class="lede">Edit anything that does not match the bill. Highlighted lines need extra attention.</p>`;
  const wrap = document.createElement("div");
  wrap.className = "table-wrap";
  const table = document.createElement("table");
  table.innerHTML = `<caption class="sr-only">Editable extracted bill lines</caption><thead><tr><th scope="col">Code</th><th scope="col">Description</th><th scope="col">Quantity</th><th scope="col">Billed amount</th></tr></thead>`;
  const body = document.createElement("tbody");

  state.lineItems.forEach((item, index) => {
    const confidence = state.confidence.find((entry) => entry.line_item_id === item.id);
    const row = document.createElement("tr");
    if (confidence?.needs_confirmation) row.className = "needs-confirmation";
    const fields = [
      ["code", item.code || "", "text"],
      ["description", item.description, "text"],
      ["quantity", item.quantity ?? "", "number"],
      ["billed_amount", item.billed_amount, "number"],
    ];
    fields.forEach(([key, value, type]) => {
      const cell = document.createElement("td");
      const label = document.createElement("label");
      label.className = "sr-only";
      label.htmlFor = `${key}-${index}`;
      label.textContent = `${key.replaceAll("_", " ")} for line ${index + 1}`;
      const input = document.createElement("input");
      input.id = label.htmlFor;
      input.type = type;
      if (type === "number") { input.min = "0"; input.step = "0.01"; }
      input.value = String(value);
      input.addEventListener("change", () => {
        item[key] = type === "number" ? (input.value === "" ? null : Number(input.value)) : (input.value || null);
      });
      cell.append(label, input);
      row.append(cell);
    });
    if (confidence?.needs_confirmation) {
      const badge = document.createElement("span");
      badge.className = "badge";
      badge.textContent = "Check this line";
      row.lastElementChild.append(badge);
    }
    body.append(row);
  });
  table.append(body); wrap.append(table); section.append(wrap);
  const actions = document.createElement("div"); actions.className = "actions";
  actions.append(button("Back", () => show("home"), true), button("Looks right", async (event) => {
    const trigger = event.currentTarget; trigger.disabled = true; trigger.textContent = "Checking…";
    try {
      state.analysisMessage = null;
      state.analysis = await analyzeBill(state.lineItems);
    } catch (error) {
      state.analysis = { line_items: state.lineItems, flags: [], price_references: [] };
      state.analysisMessage = error.message || "Analysis is not available yet.";
    }
    show("results");
  }));
  section.append(actions); main.append(section);
}

function renderResults() {
  const section = document.createElement("section");
  section.innerHTML = `<h1>Bill summary</h1>`;
  section.append(generalInfo());
  if (state.analysisMessage) section.append(notice(`${state.analysisMessage} Showing the confirmed bill without added flags.`, "notice"));
  const references = state.analysis?.price_references || [];
  const flags = state.analysis?.flags || [];

  state.lineItems.forEach((item) => {
    const card = document.createElement("article"); card.className = "card";
    const title = document.createElement("h2"); title.textContent = item.description;
    const details = document.createElement("dl"); details.className = "facts";
    addFact(details, "Code", item.code || "Not shown");
    addFact(details, "Billed amount", money(item.billed_amount));
    const ref = references.find((entry) => entry.code === item.code);
    if (ref) {
      addFact(details, "Medicare reference", moneyOrNone(ref.medicare_price));
      addFact(details, "Massachusetts range", range(ref.ma_range_low, ref.ma_range_high));
      addFact(details, "Reference", `${ref.data_source} (${ref.data_year})`);
    }
    card.append(title, details);
    const itemFlags = flags.filter((flag) => flag.line_item_id === item.id);
    if (itemFlags.length) {
      const list = document.createElement("ul"); list.className = "flags";
      itemFlags.forEach((flag) => {
        const li = document.createElement("li");
        const reason = document.createElement("strong"); reason.textContent = flag.explanation || flag.reason;
        const basis = document.createElement("span"); basis.textContent = flag.basis;
        li.append(reason, basis); list.append(li);
      });
      card.append(list);
    }
    section.append(card);
  });

  const actions = document.createElement("div"); actions.className = "actions";
  actions.append(button("Back", () => show("confirm"), true), button("Draft a letter", () => show("letter")));
  section.append(actions, renderResources()); main.append(section);
}

function renderLetter() {
  main.innerHTML = `<section><h1>Draft a letter</h1><p class="lede">Choose a letter type and add the details you want included. Review and edit the returned draft before using it. The app does not send it.</p><div class="card">
    <label for="letter-type">Letter type</label>
    <select id="letter-type"><option value="itemized_bill">Request an itemized bill</option><option value="coding_review">Ask about flagged charges</option><option value="financial_assistance">Ask about financial assistance</option></select>
    <label for="patient-name">Your name (optional)</label><input id="patient-name" autocomplete="name">
    <label for="account-number">Account number (optional)</label><input id="account-number">
    <label for="hospital-name">Provider or hospital (optional)</label><input id="hospital-name">
    <label for="letter-date">Date (optional)</label><input id="letter-date" type="date">
    <label for="letter-notes">Additional notes (optional)</label><textarea id="letter-notes" rows="4"></textarea>
    <div id="letter-message"></div><div class="actions" id="letter-actions"></div></div><div id="draft"></div></section>`;
  main.prepend(generalInfo());
  const actions = main.querySelector("#letter-actions");
  actions.append(button("Back", () => show("results"), true), button("Create draft", async (event) => {
    const trigger = event.currentTarget; trigger.disabled = true; trigger.textContent = "Drafting…";
    const message = main.querySelector("#letter-message"); message.replaceChildren();
    try {
      const result = await draftLetter({
        lineItems: state.lineItems,
        flags: state.analysis?.flags || [],
        letterType: main.querySelector("#letter-type").value,
        patient: {
          name: main.querySelector("#patient-name").value,
          account_number: main.querySelector("#account-number").value,
          hospital: main.querySelector("#hospital-name").value,
          date: main.querySelector("#letter-date").value,
          notes: main.querySelector("#letter-notes").value,
        },
      });
      renderDraft(result.draft || result.letter_draft || result);
    } catch (error) {
      message.append(notice(error.message || "Letter drafting is not available yet.", "error"));
      trigger.disabled = false; trigger.textContent = "Create draft";
    }
  }));
}

function renderDraft(draft) {
  const host = main.querySelector("#draft"); host.replaceChildren(); host.className = "card";
  const heading = document.createElement("h2"); heading.textContent = "Editable draft";
  const subjectLabel = document.createElement("label"); subjectLabel.htmlFor = "draft-subject"; subjectLabel.textContent = "Subject";
  const subject = document.createElement("input"); subject.id = "draft-subject"; subject.value = draft.subject || "";
  const bodyLabel = document.createElement("label"); bodyLabel.htmlFor = "draft-body"; bodyLabel.textContent = "Letter";
  const body = document.createElement("textarea"); body.id = "draft-body"; body.rows = 14; body.value = draft.body || "";
  const actions = document.createElement("div"); actions.className = "actions";
  actions.append(button("Copy", async (event) => {
    await navigator.clipboard.writeText(`Subject: ${subject.value}\n\n${body.value}`);
    event.currentTarget.textContent = "Copied";
  }), button("Print", () => window.print(), true));
  host.append(heading, subjectLabel, subject, bodyLabel, body, actions);
}

function renderCompare() {
  main.innerHTML = `<section><h1>Compare procedure prices</h1><p class="lede">Enter a billing code to view available Massachusetts public price data.</p><div class="card"><label for="compare-code">Billing code</label><input id="compare-code" placeholder="For example, 99213"><div id="compare-message"></div><div class="actions" id="compare-actions"></div></div><div id="compare-chart"></div></section>`;
  main.prepend(generalInfo());
  const actions = main.querySelector("#compare-actions");
  actions.append(button("Back", () => show("home"), true), button("Compare", async (event) => {
    const code = main.querySelector("#compare-code").value.trim();
    const message = main.querySelector("#compare-message"); message.replaceChildren();
    if (!code) { message.append(notice("Enter a billing code first.", "error")); return; }
    const trigger = event.currentTarget; trigger.disabled = true; trigger.textContent = "Loading…";
    try {
      const result = await fetchCompare(code, "");
      mountCompare(main.querySelector("#compare-chart"), result);
    } catch (error) {
      message.append(notice(error.message || "Price comparison is not available.", "error"));
    } finally { trigger.disabled = false; trigger.textContent = "Compare"; }
  }));
}

function renderResources() {
  const section = document.createElement("section"); section.className = "resources";
  const heading = document.createElement("h2"); heading.textContent = "Massachusetts resources";
  const list = document.createElement("ul");
  resources.forEach((resource) => {
    const li = document.createElement("li");
    const link = document.createElement("a"); link.href = resource.url; link.target = "_blank"; link.rel = "noopener noreferrer"; link.textContent = resource.label;
    const text = document.createTextNode(` — ${resource.description}`); li.append(link, text); list.append(li);
  });
  section.append(heading, list); return section;
}

function addFact(list, term, value) {
  const row = document.createElement("div"); const dt = document.createElement("dt"); const dd = document.createElement("dd");
  dt.textContent = term; dd.textContent = value; row.append(dt, dd); list.append(row);
}
function money(value) { return Number(value).toLocaleString("en-US", { style: "currency", currency: "USD" }); }
function moneyOrNone(value) { return value == null ? "Not available" : money(value); }
function range(low, high) { return low == null || high == null ? "Not available" : `${money(low)}–${money(high)}`; }
