// Pure: turn a compare API result + active payer group into a render-ready view model.
// No DOM, no network. Never fabricates a value: a null figure becomes a "none" row, not 0.

const NEGOTIATED_GROUPS = ["commercial", "medicare_advantage", "medicaid_managed"];
const GROUP_LABELS = {
  commercial: "Commercial",
  medicare_advantage: "Medicare Advantage",
  medicaid_managed: "Medicaid managed",
  cash: "Cash",
  gross: "Gross charge",
};

function money(n) {
  if (n === null || n === undefined) return null;
  return "$" + Number(n).toLocaleString("en-US", { maximumFractionDigits: 0 });
}

// Which payer groups appear in at least one hospital (for the toggle).
export function availableGroups(result) {
  const present = new Set();
  for (const h of result.hospitals || []) {
    for (const g of Object.keys(h.price_stats || {})) present.add(g);
  }
  // Stable, UI-friendly order.
  return ["commercial", "medicare_advantage", "medicaid_managed", "cash", "gross"].filter(
    (g) => present.has(g)
  );
}

function rowFor(hospital, payerGroup) {
  const ps = (hospital.price_stats || {})[payerGroup];
  const base = { hospitalId: hospital.hospital_id, name: hospital.name || hospital.hospital_id };

  if (!ps) return { ...base, kind: "none", text: "no data in these files" };

  if (payerGroup === "cash") {
    const v = ps.cash_price;
    if (v === null || v === undefined) return { ...base, kind: "none", text: "no cash price" };
    return { ...base, kind: "single", value: v, text: `cash price ${money(v)}` };
  }
  if (payerGroup === "gross") {
    const v = ps.gross_charge;
    if (v === null || v === undefined) return { ...base, kind: "none", text: "no gross charge" };
    return { ...base, kind: "single", value: v, text: `gross charge ${money(v)}` };
  }
  // Negotiated groups -> min/median/max range.
  const { min_rate: min, median_rate: median, max_rate: max } = ps;
  if (min === null || max === null || min === undefined || max === undefined) {
    return { ...base, kind: "none", text: "no negotiated range" };
  }
  const medianText = median !== null && median !== undefined ? `, median ${money(median)}` : "";
  return {
    ...base,
    kind: "range",
    min,
    median,
    max,
    text: `${money(min)}\u2013${money(max)}${medianText}`,
  };
}

function summarize(rows, payerGroup, medicarePrice) {
  const label = GROUP_LABELS[payerGroup] || payerGroup;
  const withData = rows.filter((r) => r.kind !== "none");
  if (withData.length === 0) {
    return `No ${label.toLowerCase()} figures for this service in the available data.`;
  }
  const values = [];
  for (const r of withData) {
    if (r.kind === "range") values.push(r.min, r.max);
    else if (r.kind === "single") values.push(r.value);
  }
  const lo = Math.min(...values);
  const hi = Math.max(...values);
  const n = withData.length;
  const hosp = n === 1 ? "hospital" : "hospitals";
  const med =
    medicarePrice !== null && medicarePrice !== undefined
      ? ` The Medicare reference is ${money(medicarePrice)}.`
      : " There is no Medicare reference for this code in the data.";
  return `${label} figures range from ${money(lo)} to ${money(hi)} across ${n} Massachusetts ${hosp} in this data.${med}`;
}

export function toViewModel(result, payerGroup) {
  const framingNote = result.framing_note || "";

  if (!result.found) {
    return {
      found: false,
      code: result.code,
      plainLabel: null,
      payerGroup,
      availableGroups: [],
      domain: { min: 0, max: 0 },
      rows: [],
      medicare: null,
      summary: "This code was not found in the curated list, so there is nothing to compare.",
      framingNote,
      note: result.note || "Code not found.",
    };
  }

  const groups = availableGroups(result);
  // Choose an active group that actually has data, defaulting to the requested one.
  const active = groups.includes(payerGroup) ? payerGroup : groups[0] || "commercial";

  const rows = (result.hospitals || []).map((h) => rowFor(h, active));

  const medicarePrice = result.medicare ? result.medicare.medicare_price : null;

  // Domain spans all usable figures plus the medicare reference so the line fits.
  const nums = [];
  for (const r of rows) {
    if (r.kind === "range") nums.push(r.min, r.max);
    else if (r.kind === "single") nums.push(r.value);
  }
  if (medicarePrice !== null && medicarePrice !== undefined) nums.push(medicarePrice);
  const domain = nums.length ? { min: Math.min(0, ...nums), max: Math.max(...nums) } : { min: 0, max: 0 };

  return {
    found: true,
    code: result.code,
    plainLabel: result.plain_label || result.code,
    payerGroup: active,
    availableGroups: groups,
    domain,
    rows,
    medicare:
      medicarePrice !== null && medicarePrice !== undefined
        ? { price: medicarePrice, label: `Medicare ${money(medicarePrice)}` }
        : null,
    summary: summarize(rows, active, medicarePrice),
    framingNote,
    note: null,
  };
}

export { money, GROUP_LABELS };
