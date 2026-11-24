-- An override replaces an upstream value: overriding a value only the curated layer gives means editing the curated
-- value instead.
select overrides.id
from {{ ref('stg_curated__overrides') }} as overrides
left join {{ source('raw', 'wikidata_things') }} as crosswalk on crosswalk.id = overrides.thing_id
where crosswalk.id is null
