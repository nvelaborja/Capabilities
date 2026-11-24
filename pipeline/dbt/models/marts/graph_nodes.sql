-- The built graph: every node with its full document and where it came from (ADR 0034): the curated nodes, then the
-- upstream ore minerals with their sources and mining routes (ADR 0045). A thing's quantities are the values
-- graph_facts chose, so the reasoner uses upstream values and overrides without knowing where they came from.
with chosen as (
    select node_id, json_group_object(split_part(field, '.', 2), value) as quantities
    from {{ ref('graph_facts') }}
    group by node_id
),

curated as (
    select ordinal, node_type, id, kind, label, document, json_object('layer', 'curated', 'path', path) as provenance
    from {{ ref('stg_curated__documents') }}
    -- Overrides are applied through graph_facts, not nodes of their own.
    where node_type <> 'override'
),

upstream as (
    select
        (select max(ordinal) from {{ ref('stg_curated__documents') }}) + position as ordinal,
        node_type, id, kind, label, document, provenance
    from {{ ref('stg_ore_minerals__nodes') }}
),

nodes as (
    select * from curated
    union all
    select * from upstream
)

select
    nodes.ordinal,
    nodes.node_type,
    nodes.id,
    nodes.kind,
    nodes.label,
    case
        when chosen.node_id is null then nodes.document
        else json_merge_patch(nodes.document, json_object('quantities', chosen.quantities))
    end as document,
    nodes.provenance
from nodes
left join chosen on chosen.node_id = nodes.id
order by nodes.ordinal
