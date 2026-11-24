-- A Pleiades rule places mines and quarries at one of our sources, or, for a mine that doesn't say which ore, at a
-- class (copper ore) (ADR 0046). Anything else (a material, a route) can't have places.
select rules.target, rules.word, targets.kind
from {{ source('raw', 'pleiades_sources') }} as rules
left join {{ ref('stg_curated__documents') }} as targets on targets.id = rules.target
where targets.kind is null or targets.kind not in ('source', 'category')
