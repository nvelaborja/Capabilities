-- The Wikidata crosswalk names items (Q ids), not properties or labels.
select id, wikidata
from {{ source('raw', 'wikidata_things') }}
where not regexp_full_match(wikidata, 'Q[0-9]+')
