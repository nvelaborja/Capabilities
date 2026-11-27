-- Each profile's area (ADR 0052): the union of Cliopatria's polygons for its place in every row whose years overlap the
-- profile's. Two kinds of profile:
--   curated  a profile in data/profiles with a place: the Cliopatria entity it names. One with no area stops the build.
--   seshat   a profile generated for each polity Seshat codes (ADR 0053), with the polity's years and the Cliopatria
--            polity rows (not relations) that give its Seshat id; only basic inputs, the map's, and never written to data/. A polity with no
--            such rows has none.
with polities as (
    select * from {{ ref('stg_cliopatria__polities') }}
),

curated as (
    select places.id, 'curated' as origin, null as label, null as seshat_polity, places.from_year, places.to_year,
        polities.name, polities.from_year as row_from_year, polities.to_year as row_to_year, polities.wikidata,
        polities.geometry
    from {{ ref('stg_curated__profile_places') }} as places
    join polities
        on polities.name = places.cliopatria
        and polities.from_year <= places.to_year
        and polities.to_year >= places.from_year
),

seshat_polities as (
    select distinct polity_name, polity_long_name, polity_from_year, polity_to_year
    from {{ ref('stg_seshat__codings') }}
),

seshat as (
    select 'seshat-' || seshat_polities.polity_name as id, 'seshat' as origin, seshat_polities.polity_long_name as label,
        seshat_polities.polity_name as seshat_polity, seshat_polities.polity_from_year as from_year,
        seshat_polities.polity_to_year as to_year, polities.name, polities.from_year as row_from_year,
        polities.to_year as row_to_year, polities.wikidata, polities.geometry
    from seshat_polities
    join polities
        -- A relation's row ("(Kingdom of Hawai'i nominally subject to British Empire)") carries the ids of the polities in
        -- it, and the whole relation's borders: only the polity's own rows are its area.
        on polities.type = 'POLITY'
        and list_contains(string_split(polities.seshat_ids, ';'), seshat_polities.polity_name)
        and polities.from_year <= seshat_polities.polity_to_year
        and polities.to_year >= seshat_polities.polity_from_year
),

matched as (
    select * from curated
    union all by name
    select * from seshat
),

release as (
    select release from {{ source('raw', 'upstream_snapshots') }} where dataset = 'cliopatria_polities'
),

areas as (
    select
        id,
        origin,
        any_value(label) as label,
        any_value(seshat_polity) as seshat_polity,
        -- The entity a curated profile names; for a generated one, every entity whose rows carry the polity's id.
        string_agg(distinct name, '; ' order by name) as cliopatria,
        any_value(from_year) as from_year,
        any_value(to_year) as to_year,
        count(*) as cliopatria_rows,
        -- The years Cliopatria's rows cover, which can start before the profile's and end after them.
        min(row_from_year) as cliopatria_from_year,
        max(row_to_year) as cliopatria_to_year,
        -- Rows of one entity can carry different items: the latest row's, so every build gives the same one.
        arg_max(wikidata, row_to_year) as wikidata,
        st_union_agg(geometry) as geometry
    from matched
    group by id, origin
)

select
    areas.*,
    -- For the map, which reads the built graph without a spatial library.
    st_asgeojson(areas.geometry) as geojson,
    release.release as cliopatria_release
from areas
cross join release
order by id
