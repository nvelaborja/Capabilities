-- The MRDS crosswalk may only name source kinds: deposits are occurrences of sources (ADR 0036).
select crosswalk.source_id, documents.kind
from {{ source('raw', 'mrds_sources') }} as crosswalk
join {{ ref('stg_curated__documents') }} as documents on documents.id = crosswalk.source_id
where documents.kind is distinct from 'source'
