-- Every quantity value the curated layer gives a thing: one row per thing and quantity.
select
    documents.id as thing_id,
    quantities.key as quantity,
    quantities.value::json as value,
    {{ quantity_low('quantities.value::json') }} as low,
    {{ quantity_high('quantities.value::json') }} as high
from {{ ref('stg_curated__documents') }} as documents,
    json_each(documents.document -> 'quantities') as quantities
where documents.node_type = 'thing'
