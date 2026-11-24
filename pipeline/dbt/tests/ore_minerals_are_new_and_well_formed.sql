-- An ore mineral row that builds nodes needs an id that no curated node has, and a template route to be mined like;
-- a rejected row (class none) builds nothing, so it has neither.
select ores.wikidata, ores.id, ores.class, ores.mined_like
from {{ source('raw', 'ore_minerals') }} as ores
left join {{ ref('stg_curated__documents') }} as clash on clash.id in (ores.id, ores.id || '-deposit', 'mine-' || ores.id)
left join {{ ref('stg_curated__documents') }} as template on template.id = ores.mined_like and template.node_type = 'route'
where (ores.class <> 'none' and (ores.id is null or clash.id is not null or template.id is null))
    or (ores.class = 'none' and (ores.id is not null or ores.mined_like is not null))
