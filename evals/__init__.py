"""Eval harness (`/evals`).

Runs Thomas's synthetic bills (which carry ground truth) through extraction, `/core`,
explain and letter, scores the results, and writes a markdown report. Every model call
goes through a disk cache keyed by the bill file hash.

Owner: Sam. This package does not change `/contracts`, `/core` or `/synthetic`.
"""
