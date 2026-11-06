# 0031. Call categories "classes" in the interface, and add their members in one click

- **Status:** Accepted
- **Date:** 2026-11-06

## Context

The interface called categories "any of a kind" and listed their members under "Any of these would do". The phrase was long, and it didn't name the thing. Categories can't be selected ([0017](0017-ui-selection-model.md)), because "any iron ore" doesn't say which ore, and members differ in what matters (hardness, purity, where they are found). But adding a member meant drilling into it and then pressing **Add to selected**, two steps for a common move. With only a copper chisel selected, bloom iron is one step away, and the class's details are where the user decides which ore to add.

Separately, an action whose answer doesn't depend on its target ("Move anything", shown when every load gives the same answer) couldn't be explained: its id, `move:(any)`, named no real target.

## Decision

- **The interface calls categories classes:** the legend says "Class (iron ore: any member will do)", class details list "Class members", a member's details say "Member of [class]", and "is a" lines say "member of a class". The data format and API keep the name `category`.
- **Each member in a class's details has an Add button** that adds it to the selection in one click, and shows "✓ Selected" once it is chosen.
- **`move:(any)` is explained as the verb on any target:** every route of the verb, no particular target, and what any route needing the verb leads to. It can't be selected or focused, since it isn't a single action on the graph. The reasoner names the placeholder `ANY_TARGET`.
- **Natural materials say whether they are assumed.** Ubiquitous ones read "Always available"; regional ones read "Not assumed … add it, or select something that needs it". This rule is unchanged ([0006](0006-separate-selected-implied-and-reachable.md), data format rule 2); the details now state it.

## Consequences

- The interface and the data use different words for the same thing. Contributors read "category" in data files and docs; users read "class".
- Requirement labels still say "Iron ore (any)", which reads well as "any iron ore".

## Alternatives considered

- **Let classes be selected, meaning "some member".** That hides which member, and members can give different answers (a hard abrasive versus a soft one), so results would be less certain.
- **Rename `category` in the data too.** A breaking change to every data file and the schema, for no gain in reasoning.
