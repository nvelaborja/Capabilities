// Shapes returned by the Python API (src/capabilities/views.py and server.py).

export type DrawnKind = "material" | "artifact" | "category" | "effect" | "action";
export type NodeKind = DrawnKind | "route";

/** Where a node stands relative to the current selection. */
export type Status = "selected" | "hypothetical" | "implied" | "reachable" | "maybe" | "near" | "out";

/** Three-valued answers: missing data is "maybe", never "no" (ADR 0007). */
export type Tri = "yes" | "maybe" | "no";

export type RequirementRole = "consumed" | "tool" | "effect" | "action";

export interface GraphNode {
  id: string;
  label: string;
  kind: NodeKind;
  selectable?: boolean;
  level?: number | null;
  prerequisites?: number;
  origin?: "natural" | "produced";
  availability?: "ubiquitous" | "regional";
  era?: string;
  verb?: string;
  target?: string;
  achieves?: { kind: "thing" | "effect" | "verb"; id: string };
  techniques?: string[];
}

export interface GraphEdge {
  id: string;
  source: string;
  target: string;
  kind: "requires" | "produces" | "performs" | "is_a";
  role?: RequirementRole;
  label?: string;
  byproduct?: boolean;
}

export interface GraphResponse {
  nodes: GraphNode[];
  edges: GraphEdge[];
  verbs: { id: string; label: string }[];
  techniques: { id: string; label: string }[];
}

export interface Profile {
  id: string;
  label: string;
  period?: string | null;
  region?: string | null;
  description?: string | null;
}

export interface ProfileItem {
  id?: string;
  verb?: string;
  target?: string;
  notes?: string;
}

export interface ProfileDetail extends Profile {
  includes: ProfileItem[];
}

export interface SelectionRequest {
  profile?: string | null;
  select?: string[];
  deselect?: string[];
  hypothetical?: string[];
}

export interface ExploreResponse {
  selected: string[];
  hypothetical: string[];
  implied: {
    things: string[];
    categories: string[];
    actions: string[];
    techniques: string[];
    effects: Record<string, Record<string, string>>;
  };
  reachable: string[];
  maybe: string[];
  actions: Record<string, Record<string, Tri>>;
  near_misses: { thing: string; route: string; missing: string }[];
  warnings: string[];
  status: Record<string, Status>;
  route_status: Record<string, Tri>;
  implied_by: Record<string, string[]>;
  implied_effects: { id: string; label: string; conditions: string[] }[];
  near: NearMiss[];
}

/** A thing one requirement away, with each route that would work and the one thing it is missing. */
export interface NearMiss {
  id: string;
  label: string;
  routes: { id: string; label: string; missing: { id: string; label: string; kind: string } }[];
}
