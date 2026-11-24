-- The built graph: every node with its full document and where it came from (ADR 0034). A thing's quantities are the
-- values graph_facts chose, so the reasoner uses upstream values and overrides without knowing where they came from.
with chosen as (
    select node_id, json_group_object(split_part(field, '.', 2), value) as quantities
    from {{ ref('graph_facts') }}
    group by node_id
)

select
    documents.ordinal,
    documents.node_type,
    documents.id,
    documents.kind,
    documents.label,
    case
        when chosen.node_id is null then documents.document
        else json_merge_patch(documents.document, json_object('quantities', chosen.quantities))
    end as document,
    json_object('layer', 'curated', 'path', documents.path) as provenance
from {{ ref('stg_curated__documents') }} as documents
left join chosen on chosen.node_id = documents.id
-- Overrides are applied above, not nodes of their own.
where documents.node_type <> 'override'
order by documents.ordinal
