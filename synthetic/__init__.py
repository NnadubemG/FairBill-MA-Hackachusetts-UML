"""Synthetic (fictional) hospital bills with ground truth, for evals, tests, and demos."""

from synthetic.generate import SCENARIOS, bill_from_dict, generate_bill, to_json
from synthetic.render import STYLES, render_pdf, render_text

__all__ = [
    "SCENARIOS",
    "STYLES",
    "bill_from_dict",
    "generate_bill",
    "render_pdf",
    "render_text",
    "to_json",
]
