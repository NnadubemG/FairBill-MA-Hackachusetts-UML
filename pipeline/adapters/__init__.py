"""Adapters: convert raw government source files into the clean, normalized CSVs
that the pipeline stages consume.

The pipeline stages (ncci, medicare, quantity_limits, prices/hospitals) each expect a
small CSV with specific lowercase headers -- e.g. the NCCI stage wants
``code_1,code_2,modifier_indicator`` and the medicare stage wants
``hcpcs,locality,payment_amount``. The real files published by CMS and CHIA do NOT look
like that: they are fixed-width text, multi-sheet Excel exports, or wide CSVs with
different column names and extra columns.

This package is the single seam between "raw government file" and "what a stage ingests".
Each adapter:

- reads ONE documented real-world source layout,
- selects and renames only the columns the stage needs,
- performs NO estimation -- values that are not clean are passed through verbatim so the
  stage's own parser (which already refuses to invent numbers) decides,
- writes a normalized CSV to /data/raw with the filename the stage expects
  (see pipeline.config.*_RAW).

Adapters are deliberately pure text/CSV transforms so they can be unit-tested with tiny
fixtures and without downloading the multi-hundred-MB real files.
"""

from __future__ import annotations
