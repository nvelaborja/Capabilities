-- An override replaces an upstream value: its thing must be matched to a Wikidata item, and its quantity read from
-- Wikidata. Overriding a value only the curated layer gives means editing the curated value instead.
select overrides.id
from {{ ref('stg_curated__overrides') }} as overrides
left join {{ ref('stg_crosswalk__wikidata_items') }} as crosswalk on crosswalk.thing_id = overrides.thing_id
left join {{ ref('stg_curated__quantity_properties') }} as properties on properties.quantity = overrides.quantity
where crosswalk.thing_id is null or properties.quantity is null
