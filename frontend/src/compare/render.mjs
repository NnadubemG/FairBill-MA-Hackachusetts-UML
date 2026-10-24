// Pure string builders: view model -> SVG markup + an accessible data table.
// No DOM required, so these unit-test under node. Accessibility by construction:
// role="img" + aria-label on the SVG, a parallel data table, text labels on every mark,
// and shape/stroke (not color) to distinguish the median marker and medicare line.

import { makeScale } from "./scale.mjs";
import { money } from "./viewmodel.mjs";

const ROW_H = 36;
const PAD_LEFT = 220; // room for hospital name labels
const PAD_RIGHT = 70;
const WIDTH = 720;
const TOP = 48;

function esc(s) {
  return String(s)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

export function renderSVG(vm) {
  const height = TOP + Math.max(vm.rows.length, 1) * ROW_H + 24;
  const x = makeScale(vm.domain.min, vm.domain.max || 1, PAD_LEFT, WIDTH - PAD_RIGHT);

  const parts = [];
  parts.push(
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${WIDTH} ${height}" ` +
      `role="img" aria-label="${esc(vm.summary)}" class="compare-chart">`
  );

  // Title (visible).
  parts.push(
    `<text x="16" y="24" class="chart-title">${esc(vm.plainLabel)} \u2014 ${esc(vm.payerGroup)}</text>`
  );

  if (vm.rows.length === 0) {
    parts.push(
      `<text x="16" y="${TOP + 20}" class="empty">${esc(vm.note || "No data to display.")}</text>`
    );
    parts.push("</svg>");
    return parts.join("");
  }

  // Medicare reference line (dashed = shape cue, not color-only) + label.
  if (vm.medicare) {
    const mx = x(vm.medicare.price);
    parts.push(
      `<line x1="${mx}" y1="${TOP - 8}" x2="${mx}" y2="${height - 16}" ` +
        `class="medicare-line" stroke-dasharray="5 4" aria-hidden="true" />`
    );
    parts.push(
      `<text x="${mx}" y="${TOP - 14}" text-anchor="middle" class="medicare-label">` +
        `${esc(vm.medicare.label)}</text>`
    );
  }

  vm.rows.forEach((r, i) => {
    const y = TOP + i * ROW_H + ROW_H / 2;
    // Hospital name label (text, never color-only).
    parts.push(
      `<text x="16" y="${y + 4}" class="row-label">${esc(r.name)}</text>`
    );

    if (r.kind === "none") {
      parts.push(
        `<text x="${PAD_LEFT}" y="${y + 4}" class="row-none">${esc(r.text)}</text>`
      );
      return;
    }

    if (r.kind === "single") {
      const px = x(r.value);
      // Single value = diamond marker (shape cue) + value text.
      parts.push(
        `<polygon points="${px},${y - 6} ${px + 6},${y} ${px},${y + 6} ${px - 6},${y}" ` +
          `class="single-marker" />`
      );
      parts.push(
        `<text x="${px + 12}" y="${y + 4}" class="row-value">${esc(r.text)}</text>`
      );
      return;
    }

    // range: bar from min to max + median tick (vertical, distinct shape) + value text.
    const x0 = x(r.min);
    const x1 = x(r.max);
    parts.push(
      `<rect x="${x0}" y="${y - 7}" width="${Math.max(2, x1 - x0)}" height="14" ` +
        `rx="3" class="range-bar" />`
    );
    if (r.median !== null && r.median !== undefined) {
      const mx = x(r.median);
      parts.push(
        `<rect x="${mx - 1.5}" y="${y - 11}" width="3" height="22" class="median-tick" />`
      );
    }
    parts.push(
      `<text x="${x1 + 8}" y="${y + 4}" class="row-value">${esc(r.text)}</text>`
    );
  });

  parts.push("</svg>");
  return parts.join("");
}

export function renderTable(vm) {
  const rows = vm.rows
    .map((r) => {
      if (r.kind === "range") {
        return `<tr><th scope="row">${esc(r.name)}</th><td>${esc(money(r.min))}</td>` +
          `<td>${esc(r.median != null ? money(r.median) : "\u2014")}</td>` +
          `<td>${esc(money(r.max))}</td></tr>`;
      }
      if (r.kind === "single") {
        return `<tr><th scope="row">${esc(r.name)}</th><td colspan="3">${esc(money(r.value))}</td></tr>`;
      }
      return `<tr><th scope="row">${esc(r.name)}</th><td colspan="3">no data</td></tr>`;
    })
    .join("");

  const medicareRow = vm.medicare
    ? `<tr><th scope="row">Medicare reference</th><td colspan="3">${esc(money(vm.medicare.price))}</td></tr>`
    : "";

  return (
    `<table class="compare-table">` +
    `<caption>${esc(vm.plainLabel)} \u2014 ${esc(vm.payerGroup)} prices by hospital</caption>` +
    `<thead><tr><th scope="col">Hospital</th><th scope="col">Min</th>` +
    `<th scope="col">Median</th><th scope="col">Max</th></tr></thead>` +
    `<tbody>${rows}${medicareRow}</tbody></table>`
  );
}
