import type { ExploreResponse } from "../api/types";

/** An explore response with everything empty, for tests to fill in what they need. */
export function exploreWith(overrides: Partial<ExploreResponse> = {}): ExploreResponse {
  return {
    selected: [],
    hypothetical: [],
    implied: { things: [], categories: [], actions: [], techniques: [], effects: {} },
    reachable: [],
    maybe: [],
    actions: {},
    near_misses: [],
    warnings: [],
    status: {},
    route_status: {},
    implied_by: {},
    implied_effects: [],
    near: [],
    ...overrides,
  };
}
