-- Curated working dates (data/dates, ADR 0051): the year an upstream record is known to have been worked by, from a
-- cited work, used instead of what its dataset says.
select
    id,
    document -> 'occurrence' ->> 'dataset' as dataset,
    document -> 'occurrence' ->> 'record' as record_id,
    (document ->> 'worked_by')::integer as worked_by_year,
    document ->> 'reason' as reason,
    document -> 'references' as "references",
    path
from {{ ref('stg_curated__documents') }}
where node_type = 'date'
