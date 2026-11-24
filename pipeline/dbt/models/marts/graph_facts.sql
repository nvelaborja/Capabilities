-- Where every quantity value in the graph comes from (ADR 0034, ADR 0043): one row per thing and quantity, with the
-- value the graph uses and the values it was chosen over.
--
-- Precedence: an override, then the upstream value, then the curated one. Upstream wins over curated because the
-- upstream datasets are the master set for what they cover; a curated value that disagrees stays visible, and an
-- override is how we say an upstream value is wrong.
with crosswalk as (
    select * from {{ ref('stg_crosswalk__wikidata_items') }}
),

suppressed as (
    select record_id from {{ source('raw', 'suppressed_records') }} where dataset = 'wikidata'
),

snapshot as (
    select retrieved_at from {{ source('raw', 'upstream_snapshots') }} where dataset = 'wikidata_quantities'
),

-- A thing's upstream value: every best-ranked statement of the property, as one range when there are several.
upstream as (
    select
        crosswalk.thing_id,
        properties.quantity,
        statements.record_id,
        min(statements.low) as low,
        max(statements.high) as high
    from crosswalk
    join {{ ref('stg_wikidata__quantities') }} as statements on statements.record_id = crosswalk.record_id
    join {{ ref('stg_curated__quantity_properties') }} as properties on properties.property = statements.property
    where crosswalk.record_id not in (select record_id from suppressed)
    group by all
),

curated as (
    select * from {{ ref('stg_curated__quantities') }}
),

overrides as (
    select * from {{ ref('stg_curated__overrides') }}
),

facts as (
    select
        coalesce(upstream.thing_id, curated.thing_id) as node_id,
        coalesce(upstream.quantity, curated.quantity) as quantity,
        curated.value as curated_value,
        curated.low as curated_low,
        curated.high as curated_high,
        upstream.record_id,
        {{ quantity_json('upstream.low', 'upstream.high') }} as upstream_value,
        upstream.low as upstream_low,
        upstream.high as upstream_high
    from upstream
    full outer join curated on curated.thing_id = upstream.thing_id and curated.quantity = upstream.quantity
)

select
    facts.node_id || '/quantities.' || facts.quantity as id,
    facts.node_id,
    'quantities.' || facts.quantity as field,
    case
        when overrides.id is not null then 'override'
        when facts.record_id is not null then 'upstream'
        else 'curated'
    end as layer,
    coalesce(overrides.value, facts.upstream_value, facts.curated_value) as value,
    facts.curated_value,
    facts.upstream_value,
    -- Whether the curated layer and upstream disagree: the curated value is then shown beside the upstream one, and
    -- the disagreement is worth a look (an override, or a change to the curated value).
    facts.record_id is not null and facts.curated_value is not null
        and (facts.curated_low <> facts.upstream_low or facts.curated_high <> facts.upstream_high) as disagrees,
    case when facts.record_id is not null then json_object(
        'dataset', 'wikidata',
        'record', facts.record_id,
        'url', 'https://www.wikidata.org/wiki/' || facts.record_id,
        'retrieved_at', strftime(snapshot.retrieved_at at time zone 'UTC', '%Y-%m-%dT%H:%M:%SZ')
    ) end as upstream,
    case when overrides.id is not null then json_object(
        'id', overrides.id,
        'path', overrides.path,
        'reason', overrides.reason,
        'references', overrides."references",
        'replaces', overrides.replaces_value,
        -- Upstream has changed since the override was written (or no longer has a value): review it.
        'stale', facts.record_id is null
            or overrides.replaces_low <> facts.upstream_low or overrides.replaces_high <> facts.upstream_high
    ) end as override
from facts
left join overrides on overrides.thing_id = facts.node_id and overrides.quantity = facts.quantity
left join snapshot on true
order by node_id, field
