-- Each match rule is listed once.
select source_id, field, value, deposit_type, count(*) as rows
from {{ source('raw', 'mrds_sources') }}
group by all
having count(*) > 1
