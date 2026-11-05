# 0008. Record the basis of every number and the status of every reference

- **Status:** Accepted
- **Date:** 2026-11-04 (recorded 2026-11-05)

## Context

The project aims to be scientific, and its conclusions are only as good as its numbers. Some numbers are measured in experiments, some are derived, some are estimated, and some are unknown. Some references have been read and checked, while others are cited from summaries.

## Decision

- Every number carries a **basis**: `measured`, `derived`, `estimated` or `unknown`.
- Every reference carries a **status**: `unverified` (cited, not checked), `secondary` (taken from a summary) or `verified` (someone read the source and confirmed the claim). Each says what it `supports`.
- Every route needs at least one reference.
- `TODO-source` marks a claim that still needs a source. `capabilities validate` reports evidence gaps as warnings.
- Unknown is fine; guessing is not.

## Consequences

- Users and reviewers can see how much to trust each conclusion, and contributors can find the gaps.
- Adding data takes more effort.

## Alternatives considered

- **Free-form citations only.** Easy to write, but you can't tell measured numbers from guesses.
