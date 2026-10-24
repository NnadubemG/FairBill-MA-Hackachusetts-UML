"""FairBill MA data pipeline.

Pure Python 3.12 (stdlib only). Turns large public raw data under /data/raw into
small, committed JSON bundles under /data/processed.

No network at runtime. No randomness. Deterministic: same raw inputs produce
byte-identical processed outputs. Never invents or interpolates a price.
"""
