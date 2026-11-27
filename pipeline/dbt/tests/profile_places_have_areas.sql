-- Every profile with a place has an area (ADR 0052): its place names a Cliopatria entity that has borders in the
-- profile's years. A misspelt name, or years when the entity had none, would leave the profile with no sources from the
-- map, silently; so the build stops.
select places.id, places.cliopatria, places.from_year, places.to_year
from {{ ref('stg_curated__profile_places') }} as places
left join {{ ref('profile_areas') }} as areas on areas.id = places.id
where areas.id is null
