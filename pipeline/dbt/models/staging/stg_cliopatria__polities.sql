-- Cliopatria's borders (ADR 0052): one row per entity and range of years, typed. Years are signed, negative BCE, as
-- Cliopatria writes them (ADR 0051); the range is inclusive. An entity's polygons for a year are in the row whose range
-- holds it.
select
    "Name" as name,
    -- Cliopatria writes a range that ends just before AD 1 as ending in year 0 (-14 to 0, then 1 to 5), and no range
    -- starts in 0 or ends in -1. Signed years have no year 0, so that is 1 BCE; one starting in 0 would start in AD 1.
    case "FromYear"::integer when 0 then 1 else "FromYear"::integer end as from_year,
    case "ToYear"::integer when 0 then -1 else "ToYear"::integer end as to_year,
    try_cast("Area" as double) as area_km2,
    "Type" as type,
    nullif("Wikipedia", '') as wikipedia,
    nullif("Wikidata", '') as wikidata,
    -- Several for a relation between polities, separated by semicolons.
    nullif("SeshatID", '') as seshat_ids,
    nullif("Components", '') as components,
    nullif("MemberOf", '') as member_of,
    st_geomfromwkb(geometry) as geometry
from {{ source('raw', 'cliopatria_polities') }}
