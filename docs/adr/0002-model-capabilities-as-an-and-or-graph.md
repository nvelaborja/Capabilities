# 0002. Model capabilities as an AND/OR graph with quantity constraints

- **Status:** Accepted
- **Date:** 2026-11-04 (recorded 2026-11-05)

## Context

Most things can be made in more than one way. Steel can be made by carburizing bloom iron or in a crucible. Granite can be cut by abrasive sawing or, in principle, by a diamond saw. A plain dependency graph ("steel depends on iron, charcoal, furnace") can't express alternatives. It would also wrongly make every alternative a requirement.

Many requirements are not specific things but conditions on a quantity: "heat of at least 1100 °C for 24 hours", or "an abrasive at least as hard as the stone being cut". Actions such as cutting, drilling and moving apply to many materials, with rules that depend on the material.

## Decision

We will model the domain as an AND/OR graph.

- A **thing** (material, artifact, effect, category, technique, knowledge) can be obtained by **any one** of its **routes** (OR).
- A **route** works only if **all** of its **requirements** are met (AND).
- A requirement names a thing, a **category** (any member will do), an **effect** with conditions, or an **action**. It can constrain a quantity with an absolute value, a band, or a value relative to the target (`target.hardness_mohs`).
- **Verbs** are a small fixed set of parameterized actions (`cut`, `drill`, `shape`, `finish`, `move`), so one route can cover many target materials.

## Consequences

- One graph answers all three questions: backward ("what would it take?"), forward ("what else could they do?") and feasibility ("could it be done this way?").
- Alternatives stay visible, and "certainly needed" is well defined: what every route needs.
- The reasoner has to handle cycles (heat needs fuel, fuel needs heat) and three-valued comparisons ([0007](0007-compare-ranges-with-three-answers.md)).
- Visualizations must show the difference between "any of" and "all of" ([0015](0015-build-the-web-front-end-with-react-and-cytoscape.md)).

## Alternatives considered

- **Plain dependency graph.** Can't express alternatives.
- **Rule language (Prolog, Datalog).** Expressive, but contributors would have to learn a language to add data, and ranges and uncertainty are awkward.
- **RDF/OWL ontology.** Good for interchange, but heavy for contributors, and its reasoning doesn't cover quantities or three-valued logic. We may export to it later.
