-- A record has one curated working date (ADR 0051): two would leave the build to pick between them.
select dataset, record_id, count(*) as dates
from {{ ref('stg_curated__dates') }}
group by dataset, record_id
having count(*) > 1
