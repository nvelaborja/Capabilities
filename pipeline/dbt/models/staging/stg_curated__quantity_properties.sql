-- The Wikidata property each quantity is read from (the quantity's `wikidata` field), for quantities that name one.
select id as quantity, document ->> 'wikidata' as property
from {{ ref('stg_curated__documents') }}
where node_type = 'quantity' and document ->> 'wikidata' is not null
