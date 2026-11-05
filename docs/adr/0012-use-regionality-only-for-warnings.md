# 0012. Record regionality; use it only for warnings

- **Status:** Accepted
- **Date:** 2026-11-04 (recorded 2026-11-05)

## Context

Some natural materials occur everywhere (wood, clay, fieldstone, quartz sand). Others occur only in some regions (tin ore, granite, dolerite). Modeling geography and trade properly is a large project.

## Decision

- Natural materials declare `availability: ubiquitous | regional`, with optional `regions`.
- Ubiquitous materials are free. Regional ones must be selected, implied or hypothetical.
- When a selection implies a regional material the group didn't select, we emit a **trade warning** ("tin bronze implies access to tin ore; it may have been traded").
- We do not model geography, distance or trade routes.

## Consequences

- Regionality is the main gate on reachability ([0005](0005-know-how-never-gates-reachability.md)).
- Warnings point at historically interesting questions without the tool claiming answers.

## Alternatives considered

- **Model regions and trade networks.** Out of scope for now.
- **Ignore regionality.** Everyone could reach everything made of any mineral.
