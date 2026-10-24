// Pure linear scale: map a value in [domainMin, domainMax] to a pixel x in
// [rangeMin, rangeMax]. No dependencies. Used by the chart renderer.
//
// When domainMin === domainMax (e.g. a single-value cash bar, or min === max), the
// mapping would divide by zero, so we collapse to rangeMin (a point). Output is clamped
// to the range so an out-of-domain value never draws off the chart.

export function makeScale(domainMin, domainMax, rangeMin, rangeMax) {
  const span = domainMax - domainMin;
  return function x(value) {
    if (span === 0) return rangeMin;
    const t = (value - domainMin) / span;
    const px = rangeMin + t * (rangeMax - rangeMin);
    // Clamp to [rangeMin, rangeMax] (handles rangeMin < rangeMax).
    const lo = Math.min(rangeMin, rangeMax);
    const hi = Math.max(rangeMin, rangeMax);
    return Math.max(lo, Math.min(hi, px));
  };
}
