-- Where each source kind is found (ADR 0036): MRDS deposits matched to our source kinds by the crosswalk (ADR 0041), and
-- Pleiades' ancient mines and quarries matched by its rules (ADR 0046). One row per source kind and record, so a deposit
-- with both hematite and malachite is an occurrence of each. A Pleiades copper mine doesn't say which ore was mined, so
-- it is an occurrence of the ore class, not of a mineral's deposits. Each says the year it is known to have been worked by,
-- and why (ADR 0051): a cited curated date, else its dataset's (MRDS's first production, the end of a Pleiades place's
-- earliest dated period).
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

pleiades_snapshot as (
    select retrieved_at from {{ source('raw', 'upstream_snapshots') }} where dataset = 'pleiades_places'
),

workings as (
    select * from {{ ref('stg_pleiades__workings') }}
    -- Unlocated places have no point to draw.
    where latitude is not null and longitude is not null
        and record_id not in (
            select record_id from {{ source('raw', 'suppressed_records') }} where dataset = 'pleiades'
        )
),

-- The year each Pleiades place is known to have been worked by: the end of its earliest-ending dated period, since it was
-- attested, and so worked (ADR 0046), within that period. A period that hasn't ended yet (Modern, to 2100) counts as
-- ending when the snapshot was taken. Periods whose notes give no years are left out; a place with none keeps no year.
period_ends as (
    select
        attested.record_id,
        min(least(periods.to_year, year(pleiades_snapshot.retrieved_at at time zone 'UTC'))) as worked_by_year,
        -- Two periods ending in the same year: the first label, so every build names the same one.
        arg_min(
            periods.label,
            {'end': least(periods.to_year, year(pleiades_snapshot.retrieved_at at time zone 'UTC')), 'label': periods.label}
        ) as period_label
    from (select record_id, unnest(periods) as period from workings) as attested
    join {{ ref('stg_pleiades__periods') }} as periods on periods.key = attested.period
    cross join pleiades_snapshot
    where periods.to_year is not null
    group by attested.record_id
),

-- A working matches a rule when it is of the rule's kind and names its word: as a tag, or whole in its title or
-- description.
pleiades_matches as (
    select
        rules.target as source_id,
        case when list_contains(workings.materials, lower(rules.word)) then 'tag' else 'text' end
            || ': ' || lower(rules.word) as matched_on,
        workings.*
    from workings
    join {{ source('raw', 'pleiades_sources') }} as rules
        on list_contains(workings.kinds, rules.places)
        and (
            list_contains(workings.materials, lower(rules.word))
            or regexp_matches(workings.text, '\b' || lower(rules.word) || '\b')
        )
    qualify row_number() over (partition by rules.target, workings.record_id order by matched_on) = 1
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
),

mrds as (
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
    case when worked_by_year is not null then 'first production' end as worked_by_basis,
    null as worked_by_note,
    case when worked_by_year is not null then 'worked' else 'present' end as state,
    null::integer as attested_from,
    null::integer as attested_to,
    null::varchar[] as periods,
    -- MRDS doesn't say how precise its coordinates are.
    null::boolean as approximate,
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
),

pleiades as (
select
    source_id || '/pleiades/' || record_id as id,
    source_id,
    'pleiades' as dataset,
    record_id,
    name,
    st_point(longitude, latitude) as geometry,
    longitude,
    latitude,
    null as country,
    null as admin_area,
    null as development_status,
    null as deposit_type,
    null::varchar[] as ore_minerals,
    null::varchar[] as commodities,
    null::integer as first_production_year,
    null as first_production_qualifier,
    -- Worked when it is attested, perhaps only in modern times, which still shows the material was there to be used.
    period_ends.worked_by_year,
    case when period_ends.worked_by_year is not null then 'period' end as worked_by_basis,
    period_ends.period_label as worked_by_note,
    'worked' as state,
    attested_from,
    attested_to,
    periods,
    location_precision <> 'precise' as approximate,
    matched_on,
    null as record_quality,
    url,
    json_object(
        'layer', 'upstream',
        'dataset', 'pleiades',
        'record', record_id,
        'url', url,
        'retrieved_at', strftime(pleiades_snapshot.retrieved_at at time zone 'UTC', '%Y-%m-%dT%H:%M:%SZ')
    ) as provenance
from pleiades_matches
cross join pleiades_snapshot
left join period_ends using (record_id)
),

upstream as (
    select * from mrds
    union all by name
    select * from pleiades
),

dates as (
    select * from {{ ref('stg_curated__dates') }}
)

-- A curated date wins over the dataset's, which is kept beside it; with one, a place is known to have been worked.
select
    upstream.* replace (
        coalesce(dates.worked_by_year, upstream.worked_by_year) as worked_by_year,
        case when dates.id is not null then 'curated' else upstream.worked_by_basis end as worked_by_basis,
        coalesce(dates.reason, upstream.worked_by_note) as worked_by_note,
        case when dates.id is not null then 'worked' else upstream.state end as state
    ),
    case when dates.id is not null then upstream.worked_by_year end as upstream_worked_by_year,
    dates.id as worked_by_date,
    dates."references"::varchar as worked_by_references
from upstream
left join dates on dates.dataset = upstream.dataset and dates.record_id = upstream.record_id
order by upstream.source_id, upstream.dataset, upstream.record_id
