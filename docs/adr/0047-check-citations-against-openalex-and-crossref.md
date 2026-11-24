# 0047. Check citations against OpenAlex and Crossref

- **Status:** Proposed
- **Date:** 2026-11-24

## Context

Every route cites at least one reference, with an honest `status` ([0008](0008-record-the-basis-of-every-number.md)). On 2026-11-24 the curated layer had 84 references to 41 distinct works, plus the ore crosswalk's references ([0045](0045-bring-ore-minerals-in-from-upstream-roast-sulphides-and-queue-the-gaps.md)): 43 works in all. None was `verified`: 59 uses were `unverified` and 25 `secondary`. Only 11 gave a DOI and 29 a URL. Most are books (Tylecote's *A History of Metallurgy* alone backs 11 routes); 16 are web pages, lecture notes or undated handbooks (Wikipedia, Britannica, English Heritage, UNESCO).

Nothing checked whether a cited work exists, whether its DOI leads to it, whether a link still loads, or where a reader could find a copy. The plan's M2 names OpenAlex (CC0) and Crossref (bibliographic metadata without restrictions) for this ([0034](0034-build-the-graph-from-upstream-datasets-and-a-curated-layer.md), [0037](0037-license-the-project-for-non-commercial-use-only.md)).

What the services allow, from their documentation on 2026-11-24:

- **OpenAlex** needs no key. Without one, a day's free allowance is $0.10: a search costs $0.001, a lookup by DOI nothing. A free key raises the allowance tenfold.
- **Crossref** needs no key either. Anonymous users may make one search a second, and five DOI lookups. The "polite" pool asks for an email address, which we don't send: requests identify themselves only as `dataset-snapshot/1.0`, as every download does.

## Decision

**What OpenAlex and Crossref hold for each cited work is a required upstream dataset**, `upstream/reference_candidates`, with a cold backup ([0044](0044-require-every-upstream-dataset-with-cold-backups-in-git.md)). Like the Wikidata query, what it asks for comes from the curated layer. A work is known by its citation text, so Tylecote is looked up once however many routes cite it.

- A work with a DOI is looked up by it in both services.
- A work with a year in brackets is searched for: OpenAlex by its title (what follows the year, up to the first full stop, without an edition or "as summarized in"), Crossref by the whole citation (`query.bibliographic`, made for matching citations). Five candidates each are kept.
- Anything else, a web page or an undated handbook, isn't searched: neither service lists such things.
- Every cited link is requested once, and its HTTP status kept.
- Only bibliographic fields are kept, never an abstract (Crossref's can be copyrighted).

**dbt decides the match** (`reference_checks`, a new mart: one row per work). It reads the citation's title, year and first author's surname, and compares each candidate's title by the words they share. Each work gets one result:

- `found`: the work itself, with most of its title's words, its first author, and its year give or take one;
- `review_found`: only a review of it (common for books). The work exists, but neither service lists it itself;
- `possible`: close in some of those but not all. A person should look;
- `not_found`: nothing close. Many books and reports are in neither service, so this doesn't make a work doubtful;
- `doi_disagrees`: the DOI cited leads to a different work;
- `not_searched`: a web page or undated work, whose links are checked;
- `not_checked_yet`: cited since the last download.

The mart also gives the record matched, a free copy where OpenAlex knows one, and each link's state: `works`, `refused` (the site turns automated requests away, as Britannica does) or `broken`.

**A new citation doesn't stop the build.** It is `not_checked_yet` until the candidates are downloaded again. Unlike a stale Wikidata copy, nothing the reasoner answers depends on these checks.

**The reading queue is part of the curation queue**: kind `unread_reference`, one item per work not yet verified everywhere it is cited, ranked by how many routes depend on it, offering the free copy. It comes after the ore candidates and before placing materials (`unmatched_place`).

**The app shows each check under its reference** in the detail pane: "Found in OpenAlex ↗ · free copy ↗", "Only a review of it is in OpenAlex ↗", "Possibly in OpenAlex ↗: the year differs…", "Not found in OpenAlex or Crossref", and "(broken)" or "(the site refused an automated check)" after a link.

**A check never changes a reference's `status`.** Finding a work says it exists, not that it supports the claim. A person reads it and changes the YAML.

## Consequences

- With the lookup of 2026-11-24: 16 works found, 4 known only by reviews (Craddock, Nicholson & Shaw, Martin, Penhallurick), 5 possible, 2 not found, and 16 not searched. 23 of the 24 links load; Britannica's refuses automated requests. Four found works have a free copy.
- The queue gains 43 `unread_reference` items: Craddock and Tylecote first (11 routes each), then Nicholson & Shaw and Rothenberg (7).
- A full lookup takes about a minute and a half, mostly Crossref's one search a second. It costs about $0.03 of OpenAlex's free $0.10 a day, so it can run about three times a day without a key. `OPENALEX_API_KEY`, if set, is sent, and raises that tenfold; nothing needs it.
- Tests never call the services. A local stand-in answers from the committed backup, so a download through it must give back the backup exactly.
- Matching by words is simple and will be wrong now and then: Harrell & Storemyr (2009) is "possible" against a different 1992 paper by the same first author. That is why it is never more than a pointer for a reader.
- The backup is 28 KB.

## Alternatives considered

- **Let the check upgrade `status`** when a work is found. It would make the graph look better checked than it is: a found work isn't a read work.
- **Match in Python, at download.** Keeping the download as the services' answer and scoring it in SQL means a better rule needs no new download, and the rules can be read and tested beside the other marts.
- **Search web pages too.** Neither service lists Wikipedia articles or lecture notes; the results would be noise, and cost OpenAlex credits.
- **Use Crossref's polite pool** for higher limits. It needs a contact email, which we don't send to outside services. The anonymous limits are enough for about 50 works.
- **Stop the build when a citation was added after the last lookup**, as a stale Wikidata copy does. The reasoner doesn't use the checks, so a missing check is shown as `not_checked_yet` instead.
- **Open Library or WorldCat for books**, which OpenAlex and Crossref cover poorly. They might find more of the older books; worth adding if the reading queue needs it.
