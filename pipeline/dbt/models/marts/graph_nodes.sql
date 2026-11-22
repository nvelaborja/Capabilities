-- The built graph: every node with its full document and where it came from (ADR 0034).
-- Only the curated layer feeds it for now; upstream datasets join here from milestone 1.
select
    ordinal,
    node_type,
    id,
    kind,
    label,
    document,
    json_object('layer', 'curated', 'path', path) as provenance
from {{ ref('stg_curated__documents') }}
order by ordinal
