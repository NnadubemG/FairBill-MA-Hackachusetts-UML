# Requirements Document: Synthetic bill generator

## Introduction

`/synthetic` generates fictional hospital bills together with ground truth. Sam's evals use the
bills to measure extraction and explanations. `/core` tests use them to check the engine end to
end. The demo video uses them as sample bills. Bills contain no real people, hospitals, or prices.

Ground truth is built in by construction: the generator knows which problems it injected, so the
expected flags never depend on the code under test.

## Glossary

- **Scenario**: a named recipe for a bill (clean, duplicate, high_price, unknown_code, injection, mixed).
- **Ground truth**: the line items a perfect extraction returns, the reference prices used, and the
  flags `/core` is expected to produce.
- **Style**: how a bill is printed (`plain` or `messy`). Style never changes ground truth.
- **Sample**: a committed, pre-generated bill under `synthetic/samples/`.

## Requirements

### Requirement 1: Deterministic generation

**User Story:** As a developer running evals, I want the same seed to give the same bill, so that results are reproducible.

#### Acceptance Criteria
1. WHEN `generate_bill(seed, scenario)` is called twice with the same arguments, THE generator SHALL return equal bills.
2. THE generator SHALL use only a seeded random source and no clock, network, or system randomness.
3. IF the scenario name is unknown, THEN THE generator SHALL raise `ValueError` naming the valid scenarios.

### Requirement 2: Ground truth by construction

**User Story:** As an eval author, I want exact expected results, so that I can score extraction and flags without guessing.

#### Acceptance Criteria
1. THE generator SHALL return line items, the reference prices used, bill metadata, and `expected_flags`.
2. WHEN `analyze(line_items, price_references)` from `/core` runs on a generated bill, THE result SHALL contain exactly the `(line_item_id, flag_type)` pairs in `expected_flags`.
3. THE `clean` scenario SHALL have no expected flags.
4. Each other scenario SHALL inject exactly the problems its name states, and no others.
5. THE generator SHALL NOT call `/core` to compute `expected_flags`.

### Requirement 3: Safe, fictional content

**User Story:** As the team, I want no real data in the repo, so that nothing sensitive can leak.

#### Acceptance Criteria
1. THE generator SHALL use fictional hospital and patient names that are clearly marked as fictional.
2. EVERY reference price SHALL carry `data_source` of `synthetic-demo` and an integer `data_year`.
3. THE `injection` scenario SHALL include instruction-like text inside a line description, as inert data, without changing expected flags.

### Requirement 4: Printed bills

**User Story:** As Sam, I want bills as text and PDF, so that I can test extraction on real file types.

#### Acceptance Criteria
1. THE renderer SHALL produce a plain-text bill and a PDF for any generated bill, using only the standard library.
2. THE printed bill SHALL show each line's code, printed description, quantity, date of service, and amount.
3. WHEN the style is `messy`, THE renderer SHALL change date and amount formatting and add header and footer lines, without changing ground truth.
4. THE PDF SHALL be valid (correct cross-reference table) and the same input SHALL give the same bytes.

### Requirement 5: Contract and samples

**User Story:** As a teammate, I want a documented format and ready samples, so that I can use them without asking.

#### Acceptance Criteria
1. THE contract SHALL be `contracts/synthetic-bill.schema.json` with TypeScript and Python mirrors, backward compatible with existing contracts.
2. THE repository SHALL contain committed samples for each scenario, generated with fixed seeds.
3. A test SHALL fail if a committed sample differs from what the generator now produces.
4. THE command-line tool SHALL write only inside the output folder it is given.
