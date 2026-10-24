# Requirements Document: /core checks v2 (quantity and unbundling)

## Introduction

`/core` v1 flags prices, duplicates, and codes with no reference. v2 adds the two checks that were
deferred until reference data had a shape: `quantity_implausible` and `possible_unbundling`.
Both are optional extras to `analyze`: with no data supplied, v2 behaves exactly like v1.

## Glossary

- **QuantityLimit**: a typical maximum number of units for a code, with a source and year (new contract).
- **BundlePair**: two codes that a published coding edit says are normally billed together (new contract).
  `code_1` is the primary code; `code_2` is the code that edit says should not be billed separately.
- **modifier_indicator**: `"0"` pair may not be billed together; `"1"` may be billed together only with an
  appropriate modifier; `"9"` the edit does not apply.

## Requirements

### Requirement 1: Backward-compatible entry point

**User Story:** As a teammate calling `analyze`, I want my existing calls to keep working.

#### Acceptance Criteria
1. THE system SHALL accept `analyze(items, refs)` exactly as in v1 and return the same result.
2. THE system SHALL accept optional keyword arguments `quantity_limits` and `bundle_pairs`.
3. WHEN neither is supplied, THE result SHALL equal the v1 result for the same items and refs.

### Requirement 2: Quantity check

**User Story:** As a patient, I want to know when a quantity looks unusually high for a service.

#### Acceptance Criteria
1. WHEN an item's quantity is greater than the matching limit's `max_units`, THE system SHALL emit `quantity_implausible` for that item.
2. A quantity equal to `max_units` SHALL NOT be flagged.
3. IF there is no matching limit, or the match is ambiguous, or the code is unusable, THEN THE system SHALL emit nothing.
4. IF the quantity is missing, non-finite, or not positive, or `max_units` is not positive, THEN THE system SHALL emit nothing.
5. IF the limit has a blank `data_source` or a non-integer `data_year`, THEN THE system SHALL NOT use it.
6. THE flag SHALL carry the limit's `data_source` and `data_year`, and its text SHALL state the limit.
7. Codes SHALL be matched with the same normalization as price references.

### Requirement 3: Unbundling check

**User Story:** As a patient, I want to know when two codes that are usually one service are billed separately.

#### Acceptance Criteria
1. WHEN a bill has an item with `code_1` and an item with `code_2` of the same pair, THE system SHALL emit `possible_unbundling` on the `code_2` item.
2. THE check SHALL apply only to items whose `code_system` is `CPT`, `HCPCS`, or not given.
3. WHEN both items have a service date and the dates differ, THE system SHALL emit nothing. WHEN exactly one has a date, THE system SHALL emit nothing.
4. WHEN `modifier_indicator` is `"9"` or not one of `"0"`, `"1"`, `"9"`, THE system SHALL emit nothing.
5. THE severity SHALL be `medium` for `"0"` and `low` for `"1"`.
6. IF the pair has a blank `data_source` or a non-integer `data_year`, or an unusable code, THEN THE system SHALL NOT use it.
7. THE flag SHALL name both codes, carry the pair's `data_source` and `data_year`, and SHALL say only that it may be worth asking about. It SHALL NOT claim the billing is wrong.
8. THE same pair SHALL NOT produce the same flag twice for one item.

### Requirement 4: Same safety rules as v1

#### Acceptance Criteria
1. Flag text SHALL come from fixed templates and SHALL NOT contain banned words (R8 of v1).
2. Descriptions and ids SHALL NOT appear in flag text; only validated codes and numbers may.
3. Output SHALL not depend on the order of items, limits, or pairs.
4. `analyze` SHALL NOT raise for arbitrary inputs.
5. `/core` SHALL stay pure: no network, no file access, no randomness.

### Requirement 5: Contracts and test data

#### Acceptance Criteria
1. THE contracts `quantity-limit.schema.json` and `bundle-pair.schema.json` SHALL be added with TypeScript and Python mirrors, without changing existing schemas incompatibly.
2. `SyntheticBill` SHALL gain optional `quantity_limits` and `bundle_pairs`, and the scenarios `quantity` and `unbundling`.
3. FOR every generated bill, `analyze` with its limits and pairs SHALL equal its `expected_flags`.
