# 0016. Recompute results on every selection change

- **Status:** Accepted
- **Date:** 2026-11-05

## Context

Each change to the selection changes what is implied and reachable. A "submit" button would let users batch changes when computation is slow. Today a full `explore` call takes about 2 ms on the server.

## Decision

The UI recomputes after every change, with a short debounce (about 150 ms). Any request still in flight is cancelled when a newer one starts. There is no submit button.

We will add a submit/apply step if computation becomes slow enough to make the page feel unresponsive, roughly when a typical request exceeds 200 ms. The state is structured so that adding one later only changes when the request is sent.

## Consequences

- Immediate feedback: clicking a node shows its consequences at once, which suits exploration.
- The server handles more requests. That doesn't matter locally, but caching may be needed when hosted.

## Alternatives considered

- **Submit button now.** Adds a step for no benefit at current sizes.
