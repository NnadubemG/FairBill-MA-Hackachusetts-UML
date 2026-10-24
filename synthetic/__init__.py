"""Synthetic (fictional) hospital bills with ground truth, for evals, tests, and demos."""

from synthetic.generate import SCENARIOS, bill_from_dict, generate_bill, to_json

__all__ = ["SCENARIOS", "bill_from_dict", "generate_bill", "to_json"]
