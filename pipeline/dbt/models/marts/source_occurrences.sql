-- Where each source kind is found (ADR 0036): MRDS deposits matched to our source kinds by the crosswalk (ADR 0041).
-- One row per source kind and deposit, so a deposit with both hematite and malachite is an occurrence of each.
with deposits as (
    select * from {{ ref('stg_mrds__deposits') }}
    -- A deposit without coordinates can't be placed, so it isn't an occurrence.
    where latitude is not null and longitude is not null
        -- Records the curated layer suppresses as not belonging (ADR 0034).
        and record_id not in (
            select record_id from {{ source('raw', 'suppressed_records') }} where dataset = 'mrds'
        )
),

-- The curated rules, and one for each upstream ore mineral's deposits: MRDS deposits that list it as an ore (ADR 0045).
crosswalk as (
    select source_id, field, value, deposit_type from {{ source('raw', 'mrds_sources') }}
    union all
    select id || '-deposit', 'ore', mrds_ore, null from {{ source('raw', 'ore_minerals') }} where class <> 'none'
),

snapshot as (
    select retrieved_at from {{ source('raw', 'upstream_snapshots') }} where dataset = 'mrds_deposits'
),

matches as (
    select
        crosswalk.source_id,
        crosswalk.field || ': ' || crosswalk.value as matched_on,
        deposits.*
    from deposits
    join crosswalk
        on list_contains(
            list_transform(
                case crosswalk.field when 'ore' then deposits.ore_minerals else deposits.commodities end,
                lambda item: lower(item)
            ),
            lower(crosswalk.value)
        )
        and (crosswalk.deposit_type is null or deposits.deposit_type ilike '%' || crosswalk.deposit_type || '%')
    -- Two crosswalk rows can match the same deposit to the same source kind (by ore and by commodity): keep one.
    qualify row_number() over (partition by crosswalk.source_id, deposits.record_id order by matched_on) = 1
)

select
    source_id || '/mrds/' || record_id as id,
    source_id,
    'mrds' as dataset,
    record_id,
    name,
    st_point(longitude, latitude) as geometry,
    longitude,
    latitude,
    country,
    admin_area,
    development_status,
    deposit_type,
    ore_minerals,
    commodities,
    first_production_year,
    first_production_qualifier,
    -- The year by which it is known to have been worked: its first production, unless that only says "after" a year.
    case when first_production_qualifier is distinct from 'after' then first_production_year end as worked_by_year,
    case when worked_by_year is not null then 'worked' else 'present' end as state,
    matched_on,
    record_quality,
    url,
    json_object(
        'layer', 'upstream',
        'dataset', 'mrds',
        'record', record_id,
        'url', url,
        'retrieved_at', strftime(snapshot.retrieved_at at time zone 'UTC', '%Y-%m-%dT%H:%M:%SZ')
    ) as provenance
from matches
cross join snapshot
order by source_id, record_id
