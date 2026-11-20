# 0037. License the project for non-commercial use only

- **Status:** Proposed
- **Date:** 2026-11-20
- **Supersedes (when accepted):** [0014](0014-license-code-gpl-and-data-cc-by.md)

## Context

[0014](0014-license-code-gpl-and-data-cc-by.md) licensed the code under GPL-3.0-or-later and the data under CC BY 4.0. Both allow commercial use. The maintainer's intent is that the project is free to use, read, change and share, but **never used commercially**.

Those two goals conflict in one respect. "Open source" in the strict sense (the Open Source Definition, clause 6) and "free software" both forbid restricting fields of use, commercial use included. No OSI-approved license bans commercial use. A project can be free of charge, public, and open to change for everyone who isn't a business, but then it is *source-available*, not "open source" by that definition.

The upstream datasets ([0034](0034-build-the-graph-from-upstream-datasets-and-a-curated-layer.md)) bring their own terms. Checked on 2026-11-20:

| Dataset | License | Can we use it? |
|---|---|---|
| Wikidata | CC0 | Yes |
| OpenAlex | CC0 | Yes |
| Crossref | Bibliographic metadata: facts, no restrictions. Abstracts: copyrighted by publishers or authors | Yes, but we don't store abstracts |
| USGS MRDS | US federal work, public domain | Yes |
| Pleiades | CC BY 3.0 | Yes, with attribution |
| Cliopatria (Seshat polity borders) | CC BY 4.0 | Yes, with attribution |
| Seshat databank (Equinox) | CC BY-NC-SA (the website and the README; the GitHub `LICENSE` file says CC0, so we follow the stricter terms) | Only if our data is non-commercial and share-alike |
| Mindat | Site terms forbid copying its data into another product | **No** |

Every current dependency is under a permissive license (MIT, BSD, Apache-2.0, ISC, MPL-2.0, PSF, BlueOak), so none of them limits what we choose. The planned platform tools (Dagster, dbt, Iceberg, Polaris, Kafka, Spark, Trino, SeaweedFS, MapLibre) run as separate services or libraries under Apache-2.0 or BSD terms.

The maintainer is the only author so far, so the project can be relicensed. Copies already published under GPL-3.0 and CC BY 4.0 stay under those licenses for anyone who took them. A new license applies from the commit that adopts it.

## Decision

We will license the project for non-commercial use only:

- **Code** (everything outside `data/`): **PolyForm Noncommercial License 1.0.0**. Anyone may use, change and share it for any non-commercial purpose. That includes personal use, research, teaching, and charities, schools, public bodies and similar organizations, whatever their funding source. Commercial use is not allowed.
- **Data** (`data/` and every built graph or export): **Creative Commons Attribution-NonCommercial-ShareAlike 4.0 (CC BY-NC-SA 4.0)**. This matches Seshat's terms, so Seshat-derived results may be published with the data. It also allows us to include CC0, public domain and CC BY sources with attribution.
- **We describe the project as "free and source-available for non-commercial use"**, not as "open source", so we don't claim a label the license doesn't meet.
- **Attribution:** a `NOTICE` file and an About page list every upstream dataset with its license, version and credit line, and the app credits the source of each fact through its provenance ([0034](0034-build-the-graph-from-upstream-datasets-and-a-curated-layer.md)).
- **Before ingesting any new dataset**, record its license here or in the `NOTICE` file. Datasets whose terms forbid reuse (Mindat) stay out.
- **Contributions** are accepted under the same licenses (inbound = outbound), stated in a short `CONTRIBUTING` note.

## Consequences

- Companies can't use the code or the data, including inside internal tools. That is the intent.
- The project no longer qualifies as open source for directories, package indexes' "OSI approved" filters, or programs that require an OSI license. GitHub shows it as a non-standard license.
- Some contributors avoid non-OSI licenses, which may mean fewer outside contributions.
- Share-alike: anyone who publishes an adapted version of the data must use CC BY-NC-SA 4.0 too.
- Files to change when accepted: `LICENSE`, `data/LICENSE`, `pyproject.toml` (`license = "LicenseRef-PolyForm-Noncommercial-1.0.0"`), `web/package.json` (`"license": "SEE LICENSE IN ../LICENSE"`), the README's License section, and a new `NOTICE`.
- The maintainer's own use in interviews and demos is non-commercial, so it's unaffected.

## Alternatives considered

- **AGPL-3.0 for code, CC BY-NC-SA 4.0 for data.** The code stays OSI open source, and anyone who runs a modified version as a service must publish their changes, which discourages commercial forks. But a company could still use the code commercially with its own data. Choose this if the "open source" label matters more than a full ban on commercial use of the code.
- **Keep GPL-3.0 and CC BY 4.0** ([0014](0014-license-code-gpl-and-data-cc-by.md)). Both allow commercial use, and Seshat data couldn't be included.
- **CC BY-NC-SA for code as well.** One license for everything, but Creative Commons recommends against its licenses for software: they don't deal with source code, patents or linking.
- **A custom license.** Unclear terms are worse than a well-known license.
