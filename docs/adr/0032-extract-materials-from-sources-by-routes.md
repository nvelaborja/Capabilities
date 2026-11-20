# 0032. Extract materials from sources by ordinary routes

- **Status:** Accepted
- **Date:** 2026-11-06
- **Supersedes:** "ubiquitous natural materials are free" as the only rule for found materials ([0006](0006-separate-selected-implied-and-reachable.md), data format rule 2); it now applies to sources and hand-gathered materials

## Context

Natural materials were either ubiquitous, and so free, or regional, and so had to be selected. That mixed two questions: **is it here**, and **can they get it out**. Wood was free, though felling a tree needs at least a stone axe. Granite was available to anyone who selected it, though quarrying it took tough pounders. The answer to "what would it take?" stopped one step short.

## Decision

We will separate where a resource is found from how it is extracted.

- **A new kind, `source`** (`data/things/sources/`), says where a resource is found: `availability` (ubiquitous or regional) and `regions`. Examples: standing trees, a granite outcrop, a hematite deposit. A source can be selected ("had access to the Aswan outcrop") but is never used except by extraction routes.
- **Materials taken from a source are `origin: extracted`**, and an ordinary route extracts them, with ordinary requirements. Felling timber needs standing trees and an edged tool. Quarrying granite needs the outcrop and the ability to shape granite by pounding (the measured Aswan method). Mining hematite needs a deposit and a stone hammer.
- **Materials gathered by hand as they are stay `origin: natural`** with their own availability: deadwood, plant fiber, reed, clay, water, fieldstone, quartz sand. A source would add nothing, since getting them needs no tool.
- **Wood is split** into deadwood (gathered by hand, a fuel) and timber (felled, for anything built or carved). Every route that needed "cut wood" now needs timber.
- **No new reasoning rules.** Extraction routes are routes, so implication, reachability, one step away, levels and focus all follow. A source is a raw ingredient for "one step away" ([0027](0027-count-one-step-away-as-one-raw-ingredient.md)).
- **Trade warnings follow the source.** An implied regional source warns once ("implies access to the granite outcrop, or trade with someone who had it"), not again for the material. An extracted material is regional when all its sources are, so class warnings (some iron ore) still work.
- In the interface, sources are a type of their own: ⛰️ with a yellow strip (Okabe & Ito), listed first in each column.

We start with wood, granite and hematite, then convert the remaining natural materials (flint, limestone, dolerite, malachite, cassiterite, native copper, diamond, limonite) one by one, each with a cited extraction route.

## Consequences

- Having something now implies how it was extracted, unless it was traded. For Middle Kingdom Egypt, granite now follows from the Aswan outcrop and dolerite pounding, and the profile selects the outcrop, not the granite.
- Every extraction route needs a citation, so converting the remaining materials is research work, not just data entry.
- The graph gains a column of sources at level 0, and extracted materials move up: timber is level 2, quarried granite 3.
- Having a material doesn't prove its holders extracted it; it may have been traded. Implied sources say so in their warning, but implied extraction tools (pounders for granite) don't yet.
- Loose surface material (granite boulders, alluvial diamonds, float ore) needs its own route where it matters. Each such route needs its own source.

## Alternatives considered

- **An "extraction requirements" field on natural materials.** A special case the reasoner would have to learn, outside routes.
- **Extraction actions ("quarry granite") added to every route that uses the material.** Repetitive and easy to miss; the material itself would still be free.
- **Sources as materials ("granite outcrop" as a material).** Fewer code changes, but a source would look like something you hold and use, and the graph wouldn't show where things come from.
- **Require tools for all wood.** Understates level 0: fire and the first tools came before axes.
