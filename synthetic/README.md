# /synthetic

Fictional hospital bills **with ground truth**, for evals, tests, and demos. Owned by Thomas.
No real people, hospitals, or prices. Every reference price is made up and labelled
`synthetic-demo`; never show one to a patient as a real price.

## Use it

```python
from synthetic import generate_bill, render_text, render_pdf, to_json

bill = generate_bill(seed=7, scenario="mixed")   # same arguments, same bill
bill.line_items       # what a perfect extraction returns
bill.price_references # fictional reference prices to pass to core.analyze
bill.expected_flags   # exactly the (line_item_id, flag_type) pairs /core should return
render_text(bill, "messy")   # plain-text bill
render_pdf(bill, "messy")    # PDF bytes
```

Command line (writes `bill-<scenario>-<seed>.json`, `.txt`, `.pdf`):

```
python -m synthetic --seed 7 --scenario mixed --style messy --out some/folder
python -m synthetic --samples        # regenerate the committed samples
```

The data shape is `contracts/synthetic-bill.schema.json` (`SyntheticBill`).

## Scenarios

| Scenario | What is injected | Expected flags |
| --- | --- | --- |
| `clean` | nothing | none |
| `duplicate` | one line printed twice | `duplicate_line_item` on both copies |
| `high_price` | one line at 10x the top of its range | `price_above_reference` and `price_outside_ma_range` on that line |
| `unknown_code` | one code with no reference price | `no_reference_found` on that line |
| `injection` | instruction-like text inside a line description | none (it is inert data) |
| `mixed` | duplicate, high price, and unknown code together | all of the above |

Styles change only how the bill looks, never the ground truth: `plain` (ISO dates, `$` amounts)
and `messy` (`MM/DD/YY` dates, no `$`, extra header and footer lines).

## Samples

`synthetic/samples/` holds one bill per scenario (seed 1) as JSON, text, and PDF. A test fails if
they are out of date; fix it with `python -m synthetic --samples`. Do not edit them by hand.
`.gitattributes` keeps them byte-identical across operating systems.

## For evals (Sam)

Feed the `.txt` or `.pdf` to extraction and compare the result with `line_items` in the `.json`.
`raw_description` is the text as printed; `description` is our plain-language label.
Run `core.analyze(line_items, price_references)` and compare with `expected_flags`.

## Notes

- Standard library only. `/core` stays pure; this folder is the only place that writes files, and
  only through the command line, only into the folder you name.
- Ground truth is built in by construction. It is never computed by calling `/core`.
