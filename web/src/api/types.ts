// Shapes returned by the Python API (src/capabilities/views.py and server.py).

export type DrawnKind = "source" | "material" | "artifact" | "category" | "effect" | "action";
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
  origin?: "natural" | "extracted" | "produced";
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
  verbs: Named[];
  techniques: Named[];
  /** Every verb and target pair the data allows, drawn or not, for search. */
  actions: Named[];
  /** For focus mode: what each drawn node needs whichever way it is made, at every depth (ADR 0030). */
  needs: Record<string, string[]>;
}

export interface Named {
  id: string;
  label: string;
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

// ---------------------------------------------------------------- /api/explain

export interface Reference {
  citation: string;
  doi?: string;
  url?: string;
  supports?: string;
  status?: "unverified" | "secondary" | "verified";
}

/** One direct requirement of a route, met / missing / unknown, with the reason when it isn't simply met. */
export interface RequirementRow {
  id: string;
  label: string;
  kind: string;
  role: RequirementRole;
  status: Tri;
  level: number | null;
  conditions?: string[];
  reason?: string;
  notes?: string;
}

/** One way to make a thing, reach an effect or perform an action. */
export interface RouteRow {
  id: string;
  label: string;
  techniques: Named[];
  status: Tri;
  missing: number;
  uncertain: number;
  requirements: RequirementRow[];
  references: Reference[];
  byproducts?: Named[];
  /** Effect routes: how far the effect reaches ("Temperature up to 1100–1250 °C"). */
  provides?: string[];
}

export interface ItemRow {
  id: string;
  label: string;
  kind: string;
  status: Status;
  level: number | null;
}

export interface LeadsToRow extends ItemRow {
  /** The routes that use the node to make this. */
  via: string[];
}

export interface DependencyRow {
  id: string;
  label: string;
  kind: string;
  status: Tri;
  level: number | null;
  conditions?: string[];
}

export interface About {
  description?: string | null;
  notes?: string;
  origin?: "natural" | "extracted" | "produced";
  availability?: "ubiquitous" | "regional";
  regions?: string[];
  era?: string;
  quantities?: { id: string; label: string; value: string }[];
  member_of?: Named[];
  /** Actions: what is being acted on. */
  target?: Named;
  references: Reference[];
}

export interface ExplainResponse {
  id: string;
  label: string;
  kind: string;
  status: Status;
  level: number | null;
  about: About;
  leads_to: LeadsToRow[];
  /** Things, effects and actions: each way to get it, with its direct requirements. */
  routes?: RouteRow[];
  /** Categories: the members, any of which would do. */
  members?: ItemRow[];
  /** With `all`: every certain need at every depth. */
  all?: { missing: DependencyRow[]; uncertain: DependencyRow[]; have: DependencyRow[] };
  /** Know-how: the routes it describes, and what each makes. */
  used_in?: { id: string; label: string; makes: ItemRow[] }[];
}

// ---------------------------------------------------------------- /api/explain-edge

export interface EdgeRoute extends RouteRow {
  /** The source's own requirement rows in this route (its role, threshold and whether it is met). */
  link: RequirementRow[];
  /** The target is a byproduct of this route (slag), not its goal. */
  byproduct: boolean;
}

/** Why a line joins two nodes: the routes behind it, or an "is a" link. */
export type EdgeResponse =
  | { kind: "requires"; source: ItemRow; target: ItemRow; routes: EdgeRoute[] }
  | { kind: "is_a"; source: ItemRow; target: ItemRow; used_by: string[] };

export interface EdgeRequest extends SelectionRequest {
  source: string;
  target: string;
}

export interface ExplainRequest extends SelectionRequest {
  node: string;
  all?: boolean;
}
