# Kiro log

One line per notable event: a bug a hook caught, a property-test failure, a spec
change. Newest at the bottom.

- 2026-10-24 — Bootstrapped base: steering (product/tech/structure/testing), /contracts (JSON Schema canonical + TS/Python mirrors), README, .gitignore, docs log. Source of truth is JSON Schema.
- 2026-10-24 — Spec change: added optional `date_of_service` to LineItem (backward compatible). Created spec `core-checks` (v1 scope: price flags, duplicates, no_reference_found; quantity and unbundling deferred until reference data is sourced).
- 2026-10-24 — Spec change (core-checks): added per-system code normalization (REV/DRG leading zeros, CPT exact) and Decimal-based money comparison; added TC-L7..L12, TC-P11..P14, PR10..PR11.
- 2026-10-24 — Test caught a wording bug in core: the no_reference_found template said "worth asking the hospital" instead of the approved "may be worth asking about"; fixed the template. Core tasks 1-4 done, 75 tests passing.