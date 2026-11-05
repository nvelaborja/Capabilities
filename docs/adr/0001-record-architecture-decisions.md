# 0001. Record design decisions as ADRs

- **Status:** Accepted
- **Date:** 2026-11-05

## Context

Capabilities is meant to be open-source and scientific, with contributions from people and, later, AI research skills. Design decisions were first recorded in a private design document. Contributors need to know what was decided, why, and what was rejected, without access to that document. Without a record, settled questions get reopened and changes quietly contradict earlier decisions.

## Decision

We will record every significant design decision as an Architecture Decision Record (ADR) in `docs/adr/`, following Michael Nygard's format (context, decision, consequences), plus the alternatives we considered.

- Files are numbered in order: `NNNN-short-title.md`. Copy `template.md` to start one.
- `docs/adr/README.md` is the index. Every new ADR is added to it in the same pull request.
- An **accepted** ADR is not rewritten. To change a decision, write a new ADR that supersedes it, and change only the old ADR's status line to "Superseded by NNNN".
- A **proposed** ADR can be edited freely until it is accepted.
- "Significant" means it changes the data model, the reasoning rules, the API, the user-facing behavior, the stack, or the licenses.

Decisions made before this ADR (2026-11-04) were backfilled as ADRs 0002–0014.

## Consequences

- The reasoning behind the model is public and reviewable, alongside the code and data it governs.
- Changing a decision costs a short document. That is deliberate.
- Agents working on the repo are pointed at this directory by `CLAUDE.md`.

## Alternatives considered

- **Keep decisions in the private design doc only.** Contributors can't see it.
- **Keep a single decisions log file.** Simpler, but it loses the context and alternatives, and edits to old rows hide history.
