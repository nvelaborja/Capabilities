# YAML and JSON Schema

## What it is

**YAML** is a text format for structured data (maps, lists, strings, numbers) designed to be easy for people to read and write. **JSON Schema** is a vocabulary for describing what valid JSON-shaped data looks like: which fields exist, their types, which are required, allowed values and patterns. Together they let people write the graph by hand and have a machine check every file.

## How it works

**YAML.** Indentation shows nesting; `key: value` makes a map; `- item` makes a list; `{ a: 1 }` and `[1, 2]` are compact inline forms. YAML is a superset of JSON, so any YAML document that sticks to maps, lists, strings, numbers, booleans and null can be converted to JSON losslessly. That is what lets us validate YAML with JSON Schema, and store documents as JSON in the build. Watch for YAML's implicit typing: unquoted `no` or `on` can become booleans in some parsers, and `1.10` is a number. Quote strings that look like something else.

**JSON Schema.** A schema is itself a JSON document. `"type": "object"` with `"properties"` describes fields; `"required"` lists the mandatory ones; `"enum"` restricts values; `"$ref"` reuses a definition from elsewhere; `"if"`/`"then"` applies rules conditionally, for example "a source must have `availability` and must not have `origin`". A *validator* checks a document against a schema and reports every violation with its location. We use Draft 2020-12.

**Validation in layers.** Schemas check each file on its own. Rules that span files, such as "this route requires a thing that exists", are checked in code. Rules that span the whole built graph, such as "ids are unique across every type of node", are also checked as data tests in the build ([dbt](dbt.md)).

## How we use it

The curated layer is one YAML file per node: `data/things/materials/granite.yaml`, `data/routes/quarry-granite.yaml`, and so on. The directory decides the node type, and the type decides the schema ([ADR 0004](../../adr/0004-store-the-graph-as-yaml-in-git.md), [data format](../../data-format.md)). Reviewing data is reviewing a diff in a pull request.

`capabilities validate` runs every file through its schema (`schema/*.schema.json`, sharing definitions in `defs.schema.json`) with the `jsonschema` library, then checks cross-references and evidence gaps in `packages/core/src/capabilities/validate.py`. Errors fail CI; warnings, such as a claim still marked `TODO-source`, list work to do.

## Where it lives

| What | Where |
|---|---|
| The data | `data/`, `examples/jobs/` |
| Schemas | `schema/` |
| Validator | `packages/core/src/capabilities/validate.py` |
| Format and rules | [docs/data-format.md](../../data-format.md) |

```bash
uv run capabilities validate          # errors and warnings
uv run capabilities validate --quiet  # errors only
```

## Things to know

- Run `validate` before opening a data pull request; CI runs it too.
- A schema change is a data model change: read the ADRs first, and update `docs/data-format.md` in the same pull request.
- Since [ADR 0034](../../adr/0034-build-the-graph-from-upstream-datasets-and-a-curated-layer.md), these files are the *curated layer*. Upstream datasets will join them in the build, not as YAML.

## Further reading

1. [YAML 1.2.2 specification](https://yaml.org/spec/1.2.2/): chapter 2 ("Language Overview") is a readable tour.
2. [Understanding JSON Schema](https://json-schema.org/understanding-json-schema/): the best introduction, from basic types to conditionals and `$ref`.
3. [jsonschema for Python](https://python-jsonschema.readthedocs.io/): the validator we use.
