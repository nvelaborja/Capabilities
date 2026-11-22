-- A coordinate MRDS publishes but that doesn't read as a number would silently drop a deposit from the map.
select deposits.dep_id, deposits.latitude, deposits.longitude
from {{ source('raw', 'mrds_deposits') }} as deposits
join {{ ref('stg_mrds__deposits') }} as staged on staged.record_id = deposits.dep_id
where (deposits.latitude is not null and staged.latitude is null)
    or (deposits.longitude is not null and staged.longitude is null)
