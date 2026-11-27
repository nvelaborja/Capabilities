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
  /** Signed years, [from, to] (ADR 0051); with `place`, only for a profile in space and time (ADR 0052). */
  years?: [number, number];
  place?: { cliopatria: string };
  /** The profile's area and the sources found inside it; null for a profile that is only a list. */
  map: ProfileMap | null;
}

/** Where a profile is, from Cliopatria's borders, and the sources found there (ADR 0052). */
export interface ProfileMap {
  cliopatria: string;
  years: [number, number];
  /** The years Cliopatria's rows cover, which can start before the profile's and end after them. */
  cliopatria_years: [number, number];
  cliopatria_rows: number;
  wikidata: string | null;
  release: string | null;
  sources: ProfileSource[];
}

/** A source kind found inside a profile's area: had (yes) when one place was worked by the profile's last year. */
export interface ProfileSource {
  id: string;
  label: string;
  /** source, or category for an ore class (a mine that doesn't say which ore), which can't be selected. */
  kind: string;
  availability: "yes" | "maybe";
  worked_by_then: number;
  not_known_worked: number;
  /** In the profile's own list. */
  listed: boolean;
  /** Had because of the map, and not in the list: the map added it to the selection. */
  from_map: boolean;
}

/** A profile's area on the map, and the years it is compared with. */
export interface ProfileArea {
  id: string;
  label: string;
  cliopatria: string;
  release: string | null;
  years: [number, number];
  area: AreaGeometry;
}

/** A profile's area as GeoJSON: the union of its entity's polygons. */
export type AreaGeometry =
  | { type: "Polygon"; coordinates: number[][][] }
  | { type: "MultiPolygon"; coordinates: number[][][][] }
  | { type: "GeometryCollection"; geometries: AreaGeometry[] };

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
  /** Sources the profile had from the map (ADR 0052), added to its list; absent from older servers. */
  from_map?: string[];
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
  /** The passage of the work that supports the claim, word for word (an agent's proposal always gives one, ADR 0048). */
  quote?: string;
  status?: "unverified" | "secondary" | "verified";
  /** The agent run that proposed the reference, or its quote (ADR 0049), and its summary in the repository. */
  proposed_by?: { run: string; summary: string };
  /** What the citation check found for the work (ADR 0047); only in a built graph. */
  check?: ReferenceCheck;
}

/** A cited work looked up in OpenAlex and Crossref, and this reference's link checked (ADR 0047). */
export interface ReferenceCheck {
  result: "found" | "review_found" | "possible" | "not_found" | "doi_disagrees" | "not_searched" | "not_checked_yet";
  checked_at: string | null;
  note?: string;
  /** The record matched, with a link to it. */
  match?: { service: string; url: string; title: string | null; year: number | null };
  /** A free copy of the work, where OpenAlex knows one. */
  free_copy?: string;
  /** Whether this reference's own link still loads: refused means the site turned an automated check away. */
  link?: "works" | "refused" | "broken";
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

/** A thing's value of a quantity, and where it came from (ADR 0043). */
export interface Quantity {
  id: string;
  label: string;
  value: string;
  source: QuantitySource;
}

export interface QuantitySource {
  layer: "curated" | "upstream" | "override";
  /** The upstream record, for a value from upstream or one an override replaces. */
  upstream?: { dataset: string; record: string; url: string; retrieved_at: string | null; value: string };
  /** The curated layer's value, when it differs from the upstream one. */
  curated_value?: string;
  override?: { reason: string; replaces: string; references: Reference[]; stale: boolean };
}

/** Where an upstream node came from: a mineral from its Wikidata item, a deposit's places from MRDS (no link). */
export interface NodeUpstream {
  crosswalk: string;
  dataset?: string;
  record?: string;
  url?: string;
  copied_from?: Named;
  /** The agent run that proposed the crosswalk row (ADR 0048), and its summary in the repository. */
  proposed_by?: { run: string; summary: string };
}

export interface About {
  description?: string | null;
  notes?: string;
  origin?: "natural" | "extracted" | "produced";
  availability?: "ubiquitous" | "regional";
  regions?: string[];
  era?: string;
  quantities?: Quantity[];
  member_of?: Named[];
  /** A node that came from upstream (ADR 0045): the crosswalk that brought it in, and its dataset and record or the route it copies. */
  upstream?: NodeUpstream;
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

// ---------------------------------------------------------------- /api/occurrences/{id}

/** Worked: known to have been worked (by a year, or in its attested periods). Present: no known working date (ADR 0041). */
export type OccurrenceState = "worked" | "present";

export type WorkedByBasis = "first production" | "period" | "curated";

export interface WorkingDateReference {
  citation: string;
  url?: string;
  status: string;
}

export interface PlaceProperties {
  id: string;
  source_id: string;
  /** The id of the dataset the place came from, one of the response's `datasets`. */
  dataset: string;
  name: string | null;
  country: string | null;
  admin_area: string | null;
  development_status: string | null;
  deposit_type: string | null;
  /** Signed: negative is BC, and there is no year 0 (ADR 0051). */
  worked_by_year: number | null;
  /** Where the year came from: MRDS's first production, the end of the earliest Pleiades period it is attested in, or a
   * curated date with references (ADR 0051). Null with no year. */
  worked_by_basis: WorkedByBasis | null;
  /** The period's label, or the curated date's reason. */
  worked_by_note: string | null;
  /** A curated date's references: a list from the API, a JSON string once MapLibre has handled the feature. */
  worked_by_references: WorkingDateReference[] | string | null;
  /** The end of the period that dated it: later than worked_by_year when the period hadn't ended when the data was
   * taken (Modern, to 2100). */
  worked_by_period_end: number | null;
  /** What the dataset said, when a curated date replaces it: its year, and the note it came with (for Pleiades, the
   * period it was the end of). */
  upstream_worked_by_year: number | null;
  upstream_worked_by_note: string | null;
  state: OccurrenceState;
  /** Pleiades: the years it is attested from and to (negative is BC), and the named periods (ADR 0046). */
  attested_from: number | null;
  attested_to: number | null;
  /** A list from the API; a JSON string once MapLibre has handled the feature. */
  periods: string[] | string | null;
  /** Pleiades gives only a rough area, or places it by a related place. */
  approximate: boolean | null;
  /** A place of the ore class, not of one mineral's deposits: which ore isn't recorded. */
  class_level: boolean;
  record_id: string;
  url: string | null;
  /** With a profile's area: whether the place is inside it (ADR 0052). */
  in_area?: boolean;
}

export interface PlaceFeature {
  type: "Feature";
  geometry: { type: "Point"; coordinates: [number, number] };
  properties: PlaceProperties;
}

export interface SourceSummary {
  id: string;
  label: string;
  availability?: "ubiquitous" | "regional" | null;
  regions: string[];
  /** How many places are mapped, and how many of those are known to have been worked. */
  places: number;
  worked: number;
  /** The places of an ore class the material belongs to, where which ore was mined isn't recorded (ADR 0046). */
  class_level: boolean;
}

export interface PlaceDataset {
  id: string;
  label: string;
  /** A short name for links, such as "MRDS". */
  short: string;
  home: string | null;
  /** What its places are, in a sentence, and any terms of use. */
  note: string;
  retrieved_at: string | null;
  license: string | null;
}

export interface OccurrencesResponse {
  id: string;
  label: string;
  kind: "material" | "source";
  origin?: "natural" | "extracted" | "produced" | null;
  sources: SourceSummary[];
  datasets: PlaceDataset[];
  /** The profile's area, when one was asked for and it has a place (ADR 0052). */
  profile?: ProfileArea | null;
  features: { type: "FeatureCollection"; features: PlaceFeature[] };
}
