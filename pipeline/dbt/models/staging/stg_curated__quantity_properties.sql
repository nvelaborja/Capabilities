-- The Wikidata property each quantity is read from, and the unit its values must be in (the quantity's `wikidata`
-- field), for quantities that name one.
select id as quantity, document -> 'wikidata' ->> 'property' as property, document -> 'wikidata' ->> 'unit' as unit
from {{ ref('stg_curated__documents') }}
where node_type = 'quantity' and (document -> 'wikidata') is not null
