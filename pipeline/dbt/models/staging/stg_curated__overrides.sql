-- Curated replacements for upstream values (data/overrides, ADR 0043): one row per overridden thing and quantity.
select
    id,
    document ->> 'thing' as thing_id,
    document ->> 'quantity' as quantity,
    document -> 'value' as value,
    document -> 'replaces' ->> 'dataset' as replaces_dataset,
    document -> 'replaces' -> 'value' as replaces_value,
    {{ quantity_low("document -> 'replaces' -> 'value'") }} as replaces_low,
    {{ quantity_high("document -> 'replaces' -> 'value'") }} as replaces_high,
    document ->> 'reason' as reason,
    document -> 'references' as "references",
    path
from {{ ref('stg_curated__documents') }}
where node_type = 'override'
