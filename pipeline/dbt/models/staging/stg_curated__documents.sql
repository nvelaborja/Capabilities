-- One row per curated document, with the fields every node has pulled out of its JSON.
select
    ordinal,
    node_type,
    id,
    document ->> 'kind' as kind,
    document ->> 'label' as label,
    document,
    path
from {{ source('raw', 'curated_documents') }}
