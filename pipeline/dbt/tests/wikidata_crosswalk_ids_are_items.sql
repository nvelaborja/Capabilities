-- The Wikidata crosswalks name items (Q ids), not properties or labels: the curated things', and every ore mineral's,
-- rejected ones included, since a rejection is a decision about that item.
select id, wikidata
from {{ source('raw', 'wikidata_things') }}
where not regexp_full_match(wikidata, 'Q[0-9]+')
union all
select coalesce(id, mrds_ore), wikidata
from {{ source('raw', 'ore_minerals') }}
where wikidata is null or not regexp_full_match(wikidata, 'Q[0-9]+')
