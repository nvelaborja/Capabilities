-- Which Wikidata item each of our things is: the curated things (wikidata_things, ADR 0043) and the ore minerals that
-- become upstream nodes (ore_minerals, ADR 0045). Rows reviewed and rejected (class none) build nothing.
select id as thing_id, wikidata as record_id from {{ source('raw', 'wikidata_things') }}
union all
select id as thing_id, wikidata as record_id from {{ source('raw', 'ore_minerals') }} where class <> 'none'
