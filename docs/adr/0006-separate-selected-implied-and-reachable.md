# 0006. Separate selected, hypothetical, implied and reachable

- **Status:** Accepted; the definition of near misses superseded by [0027](0027-count-one-step-away-as-one-raw-ingredient.md)
- **Date:** 2026-11-04 (recorded 2026-11-05)

## Context

Question 2 ("these people could do X; what else could they do?") starts from claims about a group, such as "Middle Kingdom Egypt had copper saws and cut granite". Some conclusions follow with certainty: anyone with tin bronze had copper and reached 1085 °C. Others are only possibilities: they could have made bellows. Mixing the two would overstate what the evidence supports.

## Decision

We will report four distinct sets.

| Set | Meaning |
|---|---|
| **Selected** | What the user says the group made or did: a profile, plus or minus the user's own choices. |
| **Hypothetical** | What-if additions. Treated like selections, but reported separately. |
| **Implied** | What **every** route to a selected item needs, applied recursively. Alternatives are never implied: if steel can be made two ways, neither way is implied, only what both share. Effect levels (heat ≥ 1085 °C) and techniques can be implied. |
| **Reachable** | Everything that can be made from selected, implied and ubiquitous materials, repeated until nothing new appears. |

We also report **near misses** (one requirement away) and **trade warnings** ([0012](0012-use-regionality-only-for-warnings.md)).

**Profiles** are curated presets of selections, such as `middle-kingdom-egypt`. Users can add to them and remove from them.

## Consequences

- Certain conclusions and possibilities stay visibly different in every interface.
- Implied effect levels count as achieved, which can feed forward into reachability ([0010](0010-merge-effect-thresholds-by-the-weakest-shared-bound.md)).

## Alternatives considered

- **One "can do" set.** Simpler, but it hides the difference between evidence and possibility.
- **Implying one route's requirements when there are alternatives (for example, the most common route).** Requires a judgment the data can't support.
