-- Pleiades' mines and quarries (ADR 0046): every place typed as a mine or a quarry, with what it names, where it is and
-- when it is attested. Pleiades records what was worked in `tags` (from the Digital Atlas of the Roman Empire: copper,
-- limestone, marble…), and sometimes only in the title or description.
with places as (
    select
        *,
        list_transform(string_split(coalesce("featureTypes", ''), ','), lambda type: trim(type)) as types
    from {{ source('raw', 'pleiades_places') }}
)

select
    id as record_id,
    nullif(title, 'Untitled') as name,
    description,
    -- "mine" is Pleiades' deprecated "mine, quarry" type, from a Barrington Atlas symbol that stands for either.
    list_filter([
        case when list_has_any(types, ['mine-2', 'mine']) then 'mine' end,
        case when list_has_any(types, ['quarry', 'mine']) then 'quarry' end
    ], lambda kind: kind is not null) as kinds,
    -- The materials it names, without DARE's bookkeeping tags (dare:major=0) or ones that repeat its type.
    list_filter(
        list_transform(string_split(coalesce(tags, ''), ','), lambda tag: lower(trim(tag))),
        lambda tag: tag <> '' and not starts_with(tag, 'dare:') and tag not in ('mine', 'quarry')
            and not starts_with(tag, 'uwhs')
    ) as materials,
    -- For matching a word in the title or description. "Iron Age" is a date, not a material (Almyras, a copper site,
    -- has remains "dated to the Iron Age").
    regexp_replace(lower(coalesce(title, '') || ' ' || coalesce(description, '')), '\biron age\b', ' ', 'g') as text,
    try_cast("reprLat" as double) as latitude,
    try_cast("reprLong" as double) as longitude,
    -- precise, or rough (a sketch map's box, or a gazetteer grid square), related (placed by a related place) or
    -- unlocated.
    "locationPrecision" as location_precision,
    try_cast("minDate" as integer) as attested_from,
    try_cast("maxDate" as integer) as attested_to,
    list_filter(string_split(coalesce("timePeriodsKeys", ''), ','), lambda period: period <> '') as periods,
    'https://pleiades.stoa.org/places/' || id as url
from places
where list_has_any(types, ['mine-2', 'mine', 'quarry'])
