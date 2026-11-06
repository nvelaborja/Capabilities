import type { GraphResponse } from "./api/types";

export type ItemKind = "source" | "material" | "artifact" | "action" | "category" | "effect" | "technique" | "route";

export interface CatalogEntry {
  label: string;
  kind: ItemKind;
}

/** Labels and kinds for any id the API can return, including actions that aren't drawn ("cut:limestone"). */
export interface Catalog {
  get(id: string): CatalogEntry;
  verb(id: string): string;
}

export function createCatalog(graph: GraphResponse): Catalog {
  const entries = new Map<string, CatalogEntry>();
  for (const node of graph.nodes) entries.set(node.id, { label: node.label, kind: node.kind });
  for (const technique of graph.techniques) entries.set(technique.id, { label: technique.label, kind: "technique" });
  const verbs = new Map(graph.verbs.map((verb) => [verb.id, verb.label]));

  return {
    verb: (id: string) => verbs.get(id) ?? id,
    get(id: string): CatalogEntry {
      const known = entries.get(id);
      if (known) return known;
      if (id.includes(":")) {
        const [verb = "", target = ""] = id.split(":", 2);
        const what = target === "(any)" ? "anything" : (entries.get(target)?.label ?? target).toLowerCase();
        return { label: `${verbs.get(verb) ?? verb} ${what}`, kind: "action" };
      }
      return { label: id, kind: "material" };
    },
  };
}
