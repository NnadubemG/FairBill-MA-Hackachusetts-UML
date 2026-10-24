// Component wiring: holds state (code, payerGroup), renders the chart + table + toggle,
// and re-renders on toggle. Rendering delegates to the pure modules so logic stays
// testable. The caller provides a compare result (dependency-injected) or a fetcher.

import { toViewModel, GROUP_LABELS } from "./viewmodel.mjs";
import { renderSVG, renderTable } from "./render.mjs";

function esc(s) {
  return String(s).replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;");
}

function renderToggle(vm) {
  if (!vm.availableGroups.length) return "";
  const buttons = vm.availableGroups
    .map((g) => {
      const pressed = g === vm.payerGroup ? "true" : "false";
      const label = GROUP_LABELS[g] || g;
      return `<button type="button" role="button" data-group="${g}" aria-pressed="${pressed}">${esc(label)}</button>`;
    })
    .join("");
  return `<div class="payer-toggle" role="group" aria-label="Payer group">${buttons}</div>`;
}

function renderAll(vm) {
  return (
    `<div class="compare-wrap">` +
    `<p class="compare-summary">${esc(vm.summary)}</p>` +
    (vm.framingNote ? `<p class="compare-framing">${esc(vm.framingNote)}</p>` : "") +
    renderToggle(vm) +
    renderSVG(vm) +
    renderTable(vm) +
    `</div>`
  );
}

// Mount the component into a DOM element. `result` is a compare API response object.
export function mountCompare(el, result, initialGroup = "commercial") {
  const state = { result, payerGroup: initialGroup };

  function draw() {
    const vm = toViewModel(state.result, state.payerGroup);
    state.payerGroup = vm.payerGroup; // normalized to an available group
    el.innerHTML = renderAll(vm);

    // Wire toggle buttons (keyboard-operable as real <button>s).
    el.querySelectorAll(".payer-toggle button").forEach((btn) => {
      btn.addEventListener("click", () => {
        state.payerGroup = btn.dataset.group;
        draw();
      });
    });
  }

  draw();
  return {
    setResult(next) {
      state.result = next;
      draw();
    },
  };
}
