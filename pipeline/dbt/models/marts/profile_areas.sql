-- Each profile's area (ADR 0052): the union of its Cliopatria entity's polygons in every row whose years overlap the
-- profile's. A profile whose place names no entity in those years has no area, which the build's tests stop on.
with places as (
    select * from {{ ref('stg_curated__profile_places') }}
),

polities as (
    select * from {{ ref('stg_cliopatria__polities') }}
),

release as (
    select release from {{ source('raw', 'upstream_snapshots') }} where dataset = 'cliopatria_polities'
),

areas as (
    select
        places.id,
        places.cliopatria,
        places.from_year,
        places.to_year,
        count(*) as cliopatria_rows,
        -- The years Cliopatria's rows cover, which can start before the profile's and end after them.
        min(polities.from_year) as cliopatria_from_year,
        max(polities.to_year) as cliopatria_to_year,
        -- Rows of one entity can carry different items: the latest row's, so every build gives the same one.
        arg_max(polities.wikidata, polities.to_year) as wikidata,
        st_union_agg(polities.geometry) as geometry
    from places
    join polities
        on polities.name = places.cliopatria
        and polities.from_year <= places.to_year
        and polities.to_year >= places.from_year
    group by all
)

select
    areas.*,
    -- For the map, which reads the built graph without a spatial library.
    st_asgeojson(areas.geometry) as geojson,
    release.release as cliopatria_release
from areas
cross join release
order by id
