# 0009. Check feasibility with performance envelopes and ballpark bands

- **Status:** Accepted
- **Date:** 2026-11-04 (recorded 2026-11-05)

## Context

Question 3 asks whether a specific job could have been done a specific way, such as "pound out this much granite with dolerite pounders". Answering it needs time, precision, force and material strength. Exact numbers are rarely available; orders of magnitude usually settle the question.

## Decision

- Routes declare a **performance envelope**: rate (per target material, per tool, with crew size), precision (as bands) and capacity. Each value has a basis ([0008](0008-record-the-basis-of-every-number.md)).
- Rates are recorded **per target material** (granite, limestone), from measurements, not from a formula.
- Quantities have **ballpark bands**: precision P0–P5 with fixed boundaries, and durations from minutes up to millennia and geological time (≥ 10,000 years).
- **Fracture toughness** is a quantity. Pounding requires a pounder at least as tough as the target.
- Heat is described by its base output (temperature and duration). Furnace volume is not used yet.
- Jobs can have several steps. Durations add up, and precision is checked on the final step. Time = volume ÷ (rate × tools working at once).
- A route is ruled out on time only if even its fastest estimate is over budget ("the generous end decides").

## Consequences

- Feasibility claims become arithmetic on cited numbers, and every missing number shows up as "insufficient data".
- Rates measured on one material can't be extrapolated to another. That is deliberate, but it means more measurements are needed.

## Alternatives considered

- **Physical formulas for removal rates.** More general, but the inputs are as uncertain as the rates themselves, and the formulas are harder to cite.
- **Exact precision values.** False precision; bands match what sources can support.
