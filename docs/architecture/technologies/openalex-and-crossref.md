# OpenAlex and Crossref

## What it is

**Crossref** is the registration agency behind most DOIs: when a publisher gives an article or a book a DOI, it deposits the work's metadata (title, authors, date, journal, references) with Crossref, and Crossref's REST API serves it to anyone. Almost none of it is subject to copyright, and it may be used for any purpose; abstracts can be the exception.

**OpenAlex** is an open index of the world's scholarly works, built from Crossref and many other sources (repositories, publishers' sites, library catalogues), with authors, institutions and open-access copies linked up. All of it is CC0. Its API answers searches and lookups as JSON.

We use both to check the works the curated layer cites: does the work exist, does its DOI lead to it, and is there a free copy someone could read ([ADR 0047](../../adr/0047-check-citations-against-openalex-and-crossref.md)).

## How it works

**DOIs.** A DOI (`10.1103/PhysRevLett.112.175502`) is a permanent identifier for a work. The part before the slash names the registrant (here the American Physical Society); `https://doi.org/<doi>` always redirects to wherever the work lives now. DOIs are case-insensitive, so compare them in lower case. Many books, older works and reports have none.

**Works and their records.** Both services call a publication a *work*. OpenAlex gives each one an id (`https://openalex.org/W2741809807`) and keeps its `doi`, `display_name` (the title), `publication_year`, `authorships` (each with an `author.display_name`), `type` (`article`, `book`, `book-review`…), and where it can be read: `open_access.oa_url` (the best open copy, a PDF or a landing page) and `best_oa_location.pdf_url` (a direct PDF, when known). Crossref's record has `DOI`, `title` (a list), `author` (each with `given` and `family`), `issued` (date parts: `[[2014]]`), `type` and `publisher`.

**Two ways to ask.**

| | OpenAlex | Crossref |
|---|---|---|
| One work by DOI | `https://api.openalex.org/works/doi:<doi>` | `https://api.crossref.org/works/<doi>` |
| A search | `/works?search=<words>` | `/works?query.bibliographic=<a whole citation>` |
| Fewer fields | `select=id,doi,display_name,…` (top-level fields only) | `select=DOI,title,…` |
| How many | `per_page=` (up to 100) | `rows=` (up to 1000; 2 to 5 is plenty for a query) |

`query.bibliographic` is made for exactly our problem: give it a reference as a person wrote it, and it ranks the works most like it, each with a relevance `score`. OpenAlex's `search` matches words in titles, abstracts and full text, so we send only the title.

**A search finds candidates, not answers.** Both return their best guesses in order, and the first is often not the work: a review of a book shares its title, and a later edition shares title and author but not the year. Deciding which candidate, if any, is the work cited is our job.

**Cost and limits.** Neither needs an account.
- OpenAlex meters usage in dollars of credit: a day's free allowance is $0.10 without a key, $1 with a free key (`api_key=` or an `Authorization: Bearer` header). A search costs $0.001, a filtered list $0.0001, and a lookup by id or DOI nothing. Ten requests a second without a key.
- Crossref has three pools. Anonymous ("public") requests may make one search or filter a second and five DOI lookups, one at a time. Adding an email address (`mailto=`) puts you in the "polite" pool, with three times the limit. Exceeding a limit returns HTTP 429.

## How we use it

`cited_works` (`pipeline/src/capabilities_pipeline/citations.py`) reads every reference in the curated layer and the ore crosswalk; a work is its citation text, so each is asked about once. The Dagster asset `upstream/reference_candidates` then, for each work:

- with a DOI: looks it up in both services;
- with a year in brackets: searches OpenAlex for its title and Crossref for the whole citation, keeping five candidates each;
- otherwise (a web page, an undated handbook): doesn't search;
- and requests every cited link once, keeping its HTTP status.

The answers are kept as published (only bibliographic fields, never an abstract), with a cold backup in `snapshots/`. dbt's `reference_checks` mart then decides: it compares each candidate's title with the cited one by the words they share, checks the first author's surname and the year, tells a review from the work, and gives each work a result (`found`, `review_found`, `possible`, `not_found`, `doi_disagrees`, `not_searched`, `not_checked_yet`), the record matched, and a free copy. The works not yet verified become the reading queue (`unread_reference` in `curation_queue`), and the detail pane shows each check under its reference.

Why both: Crossref knows every DOI and is good at matching whole citations; OpenAlex covers more than DOIs, knows where free copies are, and marks reviews as reviews. Why not let a match mark a reference verified: finding a work says it exists, not that it supports the claim. Only a person reading it can.

## Where it lives

| What | Where |
|---|---|
| Which works are cited, and the lookups | `pipeline/src/capabilities_pipeline/citations.py` (`cited_works`, `search_text`, `Lookups`) |
| The dataset and its Dagster asset | `REFERENCES` in `upstream.py`; `reference_candidates_snapshot` in `assets.py` |
| The cold backup | `snapshots/reference_candidates/` |
| Matching | `pipeline/dbt/models/staging/stg_references__*.sql`, `pipeline/dbt/models/marts/reference_checks.sql`, `pipeline/dbt/macros/citations.sql` |
| The reading queue | `unread_references` in `pipeline/dbt/models/marts/curation_queue.sql` |
| In the app | `reference_check` in `packages/core/src/capabilities/views.py`; `web/src/detail/referenceCheck.ts` |
| Tests, with no network | `pipeline/tests/test_citations.py`, the `scholarly_endpoint` and `lookups_offline` fixtures in `conftest.py` |

```bash
cd pipeline && uv run dg launch --assets 'upstream/reference_candidates'   # look every cited work up again (about 90 s)
cd .. && uv run capabilities build                                          # check them
uv run capabilities queue                                                   # the reading queue is under unread_reference
python3 -c "import duckdb; duckdb.sql(\"select result, citation, note from 'build/graph/reference_checks.parquet' order by result\").show(max_width=200)"
```

## Things to know

- **No email, so the slow pool.** We never send contact details to outside services, so Crossref treats us as anonymous: the download waits a second between searches, and a whole lookup takes about a minute and a half.
- **The free OpenAlex allowance covers about three full lookups a day.** A run costs about $0.03 of $0.10. If that ever pinches, a free key in `OPENALEX_API_KEY` is sent with every request; nothing needs one.
- **Books are often missing, or present only as reviews.** OpenAlex and Crossref grew from journals. Many books have no record of their own; what's found is a review of them in a journal, typed `book-review`. That shows the book exists, which is why `review_found` is its own result.
- **"Not found" isn't "doubtful".** A 1930 monograph or a society's web report is in neither service. The check is a pointer for a reader, never a verdict.
- **Abstracts are left out.** Crossref's can be copyrighted by their publishers ([ADR 0037](../../adr/0037-license-the-project-for-non-commercial-use-only.md)).
- **Some sites refuse scripts.** Britannica answers our link check with 403; the link is `refused`, not `broken`.
- **Tests never call either service.** A local stand-in rebuilds each response from the committed backup, so a test download must give back the backup exactly.

## Further reading

1. [OpenAlex help](https://help.openalex.org/): what OpenAlex is and covers.
2. [OpenAlex: work attributes](https://help.openalex.org/data/works/attributes/): every field of a work.
3. [OpenAlex: searching](https://help.openalex.org/api/searching/) and [getting single entities](https://help.openalex.org/api/get-single-entities/), including by DOI.
4. [OpenAlex: selecting fields](https://help.openalex.org/api/selecting-fields/).
5. [OpenAlex: authentication](https://help.openalex.org/api/authentication/) and [pricing](https://help.openalex.org/access/pricing/): keys, limits and what each kind of request costs.
6. [Crossref REST API](https://www.crossref.org/documentation/retrieve-metadata/rest-api/): the overview, and the licence of the metadata.
7. [Crossref: access and authentication](https://www.crossref.org/documentation/retrieve-metadata/rest-api/access-and-authentication/): the public, polite and Plus pools.
8. [Tips for using the Crossref REST API](https://www.crossref.org/documentation/retrieve-metadata/rest-api/tips-for-using-the-crossref-rest-api/): etiquette, caching and paging.
9. [Crossref API reference](https://api.crossref.org/swagger-ui/index.html): every route and parameter, `query.bibliographic` among them.
