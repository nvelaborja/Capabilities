# 0045. Bring ore minerals in from upstream, roast copper sulphides, and queue the gaps

- **Status:** Proposed
- **Date:** 2026-11-24

## Context

[0034](0034-build-the-graph-from-upstream-datasets-and-a-curated-layer.md) makes upstream datasets the master set for what they cover, and asks for upstream nodes in the graph and a curation queue of the gaps. Until now every node was curated. The rule for which upstream things join the graph: anything with a route to higher technology. Hiding some until selected, or grouping them by class, is acceptable if the graph gets too big.

Our routes take ore classes (copper ore, iron ore, tin ore), so an upstream mineral reaches higher technology when it belongs to one. MRDS names the ore minerals of each deposit, and Wikidata gives each mineral's chemical formula. On 2026-11-23, 139 minerals were listed as an ore on at least 20 MRDS deposits of copper, iron or tin. 100 of them matched a Wikidata mineral species by name; 39 didn't (limonite, for one, is a mixture, not a species).

A rule (listed on deposits of the metal, and containing it) admits minerals that don't belong:
- turquoise and torbernite as copper ores, and ilmenite and chromite as iron ores: they contain the metal, but we have no evidence they were smelted for it;
- pyrite as an iron ore: "more or less useless for making iron" (Föll, Kiel lecture notes);
- the copper sulphides (chalcopyrite on 10,485 copper deposits, chalcocite, bornite), which carbon can't reduce. They are roasted first: heated on an open bed of burning charcoal, with air reaching the ore, so the sulphur burns off and oxides remain, which are then smelted. Copper-iron sulphides were often taken through more steps: melted to a sulphide matte, roasted again, then reduced (Haubner & Strobl 2023). No route did that.

And sometimes the evidence is missing: chrysocolla is common in oxidised copper ores, but the sources we could read don't say it was smelted.

## Decision

**Membership is curated, in a hand-kept table.** `data/crosswalks/ore_minerals.csv` has a row per mineral: our id, the Wikidata item, the MRDS ore name, the ore class, the curated route it is mined like (`mined_like`), and the reference that puts it in the class (citation, link, what it supports). A row with class `none` records a mineral reviewed and rejected (pyrite), with the reference that says why.

**Each row becomes three upstream nodes,** built in dbt (`stg_ore_minerals__nodes`) and appended to `graph_nodes` after the curated nodes:
- the mineral: a material in its class, `origin: extracted`, named and described from Wikidata (label, description, formula), citing the row's reference, with its quantities from Wikidata ([0043](0043-take-quantities-from-wikidata-with-upstream-first-and-overrides.md));
- its deposits: a regional source, whose places are the MRDS deposits that list it as an ore mineral, so it shows on the map ([0042](0042-show-where-things-are-found-on-a-maplibre-map.md));
- a mining route: the `mined_like` route, with the mineral and its deposit in place of the template's, and the template's references and notes.

Each node's provenance names the Wikidata item, the crosswalk and the template. The detail pane says "From Wikidata (Q…), brought in by data/crosswalks/ore_minerals.csv".

**Copper sulphides are roasted.** A curated class, copper sulphide ore, and a route, roasting copper sulphide ore, which makes roasted copper ore, a member of copper ore. So a sulphide is mined, roasted, then smelted by the existing route. The matte steps for copper-iron sulphides are folded into the one route, and said so in its notes. Iron and tin sulphides get no route: pyrite is rejected, and stannite stays in the queue.

**The first rows**, each with a reference we read:
- copper ore: azurite, cuprite and tenorite (Calgaro et al. 2023);
- copper sulphide ore: chalcocite and bornite (Calgaro et al. 2023), and chalcopyrite (Haubner & Strobl 2023);
- iron ore: magnetite and goethite (Hamilton 2007, Expedition), and siderite (Föll);
- rejected: pyrite (Föll).

**A second Wikidata snapshot**, `wikidata_items` (each crosswalked item's label, description and formula), required and backed up like the others ([0044](0044-require-every-upstream-dataset-with-cold-backups-in-git.md)). Both Wikidata queries ask about the items of both crosswalks.

**The curation queue** is a mart, `curation_queue.parquet`, with one row per gap, most valuable first within each kind:
- `ore_candidate`: an MRDS ore mineral listed on at least 20 copper, iron or tin deposits, not yet reviewed in either crosswalk, ranked by deposits;
- `extracted_without_route`, `source_without_places`;
- `route_unverified`: every reference unchecked;
- `upstream_disagreement`, `stale_override` (from `graph_facts`).

`uv run capabilities queue` prints it. Working the queue means adding a row to the ore crosswalk (taken, with a reference, or rejected), a route, or a check of a reference.

## Consequences

- The graph has 197 nodes, 27 of them from upstream. Occurrences rise from 14,488 to 35,311, most of them chalcopyrite (11,316) and magnetite (3,313).
- The graph view draws the new nodes as it draws curated ones. At this size there was no need to hide or group them; if the crosswalk grows to hundreds of minerals, grouping by class is the next step.
- Copper is now reachable from a sulphide deposit and stone tools: mined, roasted, smelted.
- A node's "Leads to" now follows class membership as the reasoner does: a route that asks for a class counts for each member, labelled "(as copper ore)", unless the member's known values fail the requirement's conditions (a copper chisel doesn't lead to cutting granite). Before, every member of a class (malachite and hematite too) showed nothing there.
- In the worked example, Egypt is one step from iron through any of five iron ores (magnetite, goethite and siderite deposits besides hematite and bog iron), and can cut, drill and finish the new minerals. The answers to the example's jobs are unchanged.
- The first queue holds 135 ore candidates (galena and sphalerite, on 6,326 and 5,051 deposits, at the top), 46 routes with only unverified references, and 2 sources with no places (bog iron, dolerite). Many candidates aren't ores of these metals at all; rejecting them is curation work too, and the evidence for each is one query away.
- The crosswalk's references are credited in CREDITS.md like the curated layer's.
- The build directory's format version is 4.
- Composition (the formula containing the metal) isn't used yet to rank or filter candidates. It would need a Wikidata lookup of every candidate by name; agents (M3) are the natural place for it.

## Alternatives considered

- **A rule: listed on deposits of the metal, and containing it.** No curation, but it admits minerals with no evidence of being smelted (turquoise, ilmenite), pyrite, and the sulphides as if they smelted like oxides.
- **The rule, with exceptions.** Still wrong by default for every new mineral, and the exceptions would be the same hand-kept table, written the other way round.
- **One generic source per class ("copper ore deposit").** Fewer nodes, but the map and the reasoner could no longer tell azurite from chalcopyrite, and a sulphide needs a different route.
- **Leave sulphides out until roasting is modelled in detail (separate roast, matte and converting routes).** More faithful for copper-iron sulphides, but nothing in the graph needs that distinction yet; the single route says what it folds together.
- **Generate routes in Python.** The build's transformations are dbt models ([0038](0038-serve-the-app-from-a-built-graph-artifact.md)); cloning a template route is a JSON patch there, tested like the rest.
