-- MRDS deposits with typed columns: one row per deposit, with its ore minerals and commodities as lists.
with deposits as (
    select * from {{ source('raw', 'mrds_deposits') }}
)

select
    dep_id as record_id,
    site_name as name,
    url,
    try_cast(latitude as double) as latitude,
    try_cast(longitude as double) as longitude,
    country,
    state as admin_area,
    dev_stat as development_status,
    dep_type as deposit_type,
    -- MRDS separates list items with commas, and some commodity names contain one ("Limestone, General"). Splitting
    -- them too is harmless: the crosswalk matches whole items, such as "Limestone".
    list_filter(list_transform(string_split(ore, ','), lambda item: trim(item)), lambda item: item <> '') as ore_minerals,
    list_filter(
        list_transform(string_split(concat_ws(',', commod1, commod2, commod3), ','), lambda item: trim(item)),
        lambda item: item <> ''
    ) as commodities,
    try_cast(yr_fst_prd as integer) as first_production_year,
    -- MRDS: "<" means production first began before that year, ">" after it.
    case yfp_ba when '<' then 'before' when '>' then 'after' end as first_production_qualifier,
    score as record_quality
from deposits
