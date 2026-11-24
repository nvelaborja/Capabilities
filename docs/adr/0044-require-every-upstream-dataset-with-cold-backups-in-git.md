# 0044. Require every upstream dataset, with cold backups in git

- **Status:** Accepted
- **Date:** 2026-11-24
- **Supersedes:** in part, [0041](0041-place-sources-with-mrds-deposits-through-a-crosswalk.md) (a build without a snapshot loads an empty table) and [0043](0043-take-quantities-from-wikidata-with-upstream-first-and-overrides.md) (curated values that match upstream stay)

## Context

Until now an upstream dataset was optional. With no snapshot, [0041](0041-place-sources-with-mrds-deposits-through-a-crosswalk.md) loaded an empty table: CI and a fresh clone built a graph with no occurrences. [0043](0043-take-quantities-from-wikidata-with-upstream-first-and-overrides.md) kept curated values that match Wikidata, so that such a build still had them.

That makes a build's answers depend on whether someone happened to download something. A graph without MRDS has no places; without Wikidata, the hardness of the materials Wikidata covers would have to be copied into the curated layer, where it duplicates upstream and goes stale. Upstream datasets are the master set for what they cover ([0034](0034-build-the-graph-from-upstream-datasets-and-a-curated-layer.md)), so the graph isn't complete without them.

But a download can't be counted on either: we work offline, CI has no reason to call USGS or Wikidata on every run, and servers go down.

On 2026-11-24 the MRDS snapshot was 32 MB as downloaded (Parquet), 15 MB recompressed with zstd at level 19; the Wikidata snapshot was 4 KB. Both datasets may be redistributed: MRDS is US public domain, Wikidata CC0.

## Decision

**Every upstream dataset is required.** A build uses a copy of each, and stops before building anything if a dataset has none, naming it and how to get one. The commands and the server build first, so they don't start without one either.

**A cold backup of each, in git.** `snapshots/<dataset>/` holds the dataset as downloaded, every value unchanged, as zstd-compressed Parquet, with its `snapshot.json` (where and when it was retrieved, the download's hash, its license). `snapshots/README.md` says whose licenses apply.

**The newest copy wins.** A build uses the latest download in `build/upstream/` or the cold backup, whichever was retrieved later, and the manifest records which (`copy`: `download` or `backup`). So a fresh clone, CI and an offline laptop build from the backups, and a new download is used as soon as it exists.

**Downloads fall back to the backup.** If a download fails because of the network (offline, a refused connection, a timeout), the Dagster asset uses the cold backup instead, logs a warning, and records the copy and the error in its metadata. Any other failure, such as a dataset whose columns changed, still fails: that needs a change to the code, not a backup.

**Backups are refreshed on purpose.** `uv run capabilities backup` makes each download that is newer than its backup the new backup. The change is committed and reviewed like any other.

**No curated copies of upstream values.** A curated value that upstream supplies is removed: the hardness of the 11 materials Wikidata gives one now comes only from Wikidata, and the references that backed only those values go with them. Curated values remain where upstream has none (flint, dolerite, quartz sand, steels, bloom iron and the artifacts).

## Consequences

- A build is complete or doesn't happen: every graph has MRDS's places and Wikidata's values.
- The repository grows by about 15 MB now, and by about as much each time MRDS's backup is refreshed, since git keeps every version. MRDS last changed in 2022, so that is rare. Larger datasets (Pleiades, slice 4c) will need the same check before they are added.
- CI builds from the backups and makes no network calls, as before.
- The worked examples give the same answers as before, from the backups alone.
- `snapshots/*/snapshot.json` is part of the build's fingerprint, so refreshing a backup makes the graph stale.
- Tests that need a dataset missing remove its backup from a copy of the data. The test copy links to the real backups rather than copying 15 MB each time.
- In [0043](0043-take-quantities-from-wikidata-with-upstream-first-and-overrides.md), an override is marked stale when Wikidata has no value for it. With the snapshot always present, that now means Wikidata really has none.

## Alternatives considered

- **Keep datasets optional (0041), with curated copies of upstream values (0043).** Builds then differ by what was downloaded, and curated copies duplicate upstream.
- **Git LFS for the backups.** Keeps the repository small, but needs LFS installed everywhere, and GitHub's free LFS bandwidth is limited; CI would spend it on every run.
- **Backups as GitHub release assets, or in object storage.** Small repository, but fetching them needs the network, which is what a cold backup is for. Worth revisiting with the lakehouse (M5), when there is object storage to keep them in.
- **Fail the download instead of falling back.** Clear, but then an offline "materialize all" fails although a good copy is at hand. The fallback is logged and recorded, so it isn't silent.
- **Refresh the backup on every download.** No extra step, but every download would change files in git, and a bad upstream change would reach the backup without review.
