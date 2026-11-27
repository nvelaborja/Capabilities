-- The occurrences inside each profile's area (ADR 0052), and whether each was worked by the profile's last year. The map
-- marks them, and profile_sources counts them. Kept apart from source_occurrences: a place is inside many profiles.
with areas as (
    select id as profile_id, to_year, geometry from {{ ref('profile_areas') }}
)

select
    areas.profile_id || '/' || occurrences.id as id,
    areas.profile_id,
    occurrences.id as occurrence_id,
    occurrences.source_id,
    coalesce(occurrences.worked_by_year <= areas.to_year, false) as worked_by_then
from areas
-- The cast is for an empty build, as in the occurrences' own test: an empty Parquet file has no geometry type.
join {{ ref('source_occurrences') }} as occurrences on st_contains(areas.geometry, occurrences.geometry::geometry)
order by areas.profile_id, occurrences.id
