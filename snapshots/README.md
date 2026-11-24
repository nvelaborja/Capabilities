# Cold backups of the upstream datasets

Every upstream dataset is required to build the graph ([ADR 0044](../docs/adr/0044-require-every-upstream-dataset-with-cold-backups-in-git.md)). These are the backups: a copy of each, kept in git, so the graph builds offline, in CI, and when a download fails.

A build uses the newest copy of each dataset, the latest download in `build/upstream/` or the backup here, and stops if a dataset has neither. To refresh the backups after downloading:

```bash
cd pipeline && uv run dg launch --assets 'upstream/mrds_deposits'          # or upstream/wikidata_quantities, upstream/pleiades_places, upstream/reference_candidates
cd .. && uv run capabilities backup                                       # copies newer downloads here
```

Commit the result. Each folder holds the dataset as downloaded, every value unchanged (Parquet, compressed with zstd), and its `snapshot.json`: where and when it was retrieved, the hash of the download, and its license.

These copies are the datasets' own, not the project's: their licenses, below, apply to them, not this repository's ([CREDITS.md](../CREDITS.md)).

| Folder | Dataset | License |
|---|---|---|
| `mrds_deposits/` | USGS Mineral Resources Data System (MRDS) | US public domain (a work of the U.S. Geological Survey) |
| `wikidata_quantities/` | Wikidata: Mohs hardness statements of the items in `data/crosswalks/wikidata_things.csv` and `ore_minerals.csv` | CC0 1.0 |
| `wikidata_items/` | Wikidata: the English label, description and chemical formula of the same items | CC0 1.0 |
| `pleiades_places/` | Pleiades: every place in the gazetteer of ancient places, from its daily dump. Credit: Pleiades contributors, *Pleiades: A Gazetteer of Past Places*, https://pleiades.stoa.org | CC BY 3.0 |
| `reference_candidates/` | What OpenAlex and Crossref hold for each work the curated layer cites (bibliographic fields only, no abstracts), and the HTTP status of each cited link | OpenAlex: CC0 1.0. Crossref: bibliographic metadata, no restrictions |
