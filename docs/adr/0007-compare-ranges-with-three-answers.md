# 0007. Compare ranges with three answers; missing data is "maybe"

- **Status:** Accepted
- **Date:** 2026-11-04 (recorded 2026-11-05)

## Context

Most quantities are uncertain ranges. Copper's hardness is 2.5–3 Mohs, and a furnace reaches somewhere between 1100 and 1250 °C. Some values are unknown: dolerite's fracture toughness hasn't been sourced. A yes/no answer would either overclaim or wrongly rule things out.

## Decision

- Comparisons return **yes** (true for every value in the ranges), **no** (true for none) or **maybe** (they overlap).
- **Missing data gives "maybe", never "no".**
- An effect route's `provides` values are the **most** it can deliver. A range means that maximum is uncertain. A furnace providing 1100–1250 °C satisfies "≥ 1100 °C" (yes) and "≥ 1200 °C" (maybe).
- Verdicts never say "impossible". The strongest negative is "no known route meets these constraints".

## Consequences

- Results are honest about uncertainty, and "maybe" points at exactly which data is missing.
- More results are "maybe" than a two-valued system would give. Interfaces must show "maybe" clearly.

## Alternatives considered

- **Use midpoints.** Hides uncertainty and can flip answers.
- **Treat missing data as "no".** Rules things out for lack of data, the opposite of scientific caution.
