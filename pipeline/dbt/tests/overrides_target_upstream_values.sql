-- An override replaces an upstream value: its thing must be matched to a Wikidata item, and its quantity read from
-- Wikidata. Overriding a value only the curated layer gives means editing the curated value instead.
select overrides.id
from {{ ref('stg_curated__overrides') }} as overrides
left join {{ source('raw', 'wikidata_things') }} as crosswalk on crosswalk.id = overrides.thing_id
left join {{ ref('stg_curated__quantity_properties') }} as properties on properties.quantity = overrides.quantity
where crosswalk.id is null or properties.quantity is null
