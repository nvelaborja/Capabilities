-- Every reference in the graph, one row per use (ADR 0047): in the curated documents (nodes, overrides, example jobs)
-- and in the upstream nodes (an ore mineral's reference, and the references a copied mining route keeps). A work is
-- known by its citation, so a book cited by eleven routes is checked once.
with documents as (
    select id as node_id, node_type, document, false as copied from {{ ref('stg_curated__documents') }}
    union all
    -- A copied mining route's references are its template's, marked unverified for the new mineral (ADR 0045): a
    -- person reads the work, and verifies it, in the template.
    select id, node_type, document, node_type = 'route' from {{ ref('stg_ore_minerals__nodes') }}
)

select
    documents.node_id,
    documents.node_type,
    {{ trim_space("tree.value ->> 'citation'") }} as citation,
    nullif({{ trim_space("tree.value ->> 'doi'") }}, '') as doi,
    nullif({{ trim_space("tree.value ->> 'url'") }}, '') as url,
    tree.value ->> 'status' as status,
    documents.copied
from documents, json_tree(documents.document) as tree
where tree.type = 'OBJECT' and tree.value ->> 'citation' is not null and tree.value ->> 'status' is not null
