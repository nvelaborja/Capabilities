# 0014. License the code under GPL-3.0-or-later and the data under CC BY 4.0

- **Status:** Accepted
- **Date:** 2026-11-04 (recorded 2026-11-05)

## Context

The project is open-source. Code and data have different reuse needs. Software derived from the code should stay open. The data should be reusable in research, teaching and publications with credit.

## Decision

- **Code** (everything outside `data/`): GNU GPL v3.0 or later (`LICENSE`).
- **Data** (`data/`): Creative Commons Attribution 4.0 International (`data/LICENSE`).

## Consequences

- Derived software must stay open under the GPL.
- Anyone can reuse and adapt the data for any purpose with attribution, including commercial and academic work.
- Dependencies must be GPL-compatible. Check licenses before adding one. For example, the ELK layout engine is EPL-2.0, which needs checking.

## Alternatives considered

- **MIT for code.** More permissive, but derived tools could close.
- **CC BY-SA or ODbL for data.** Share-alike would discourage academic reuse.
- **CC0 for data.** No attribution, which matters for a citable scientific resource.
