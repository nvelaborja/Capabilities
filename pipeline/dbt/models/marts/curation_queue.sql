-- The curation queue (ADR 0034, ADR 0045): the gaps the build finds, as a to-do list for people and, from M3, agents.
-- One row per item, most valuable first within each kind:
--   ore_candidate             a mineral MRDS lists as an ore on many copper, iron or tin deposits, not yet reviewed
--   extracted_without_route   a material said to be extracted that no route extracts
--   source_without_places     a regional source with no mapped places
--   route_unverified          a route whose references are all unchecked
--   upstream_disagreement     a curated value that differs from upstream's
--   stale_override            an override of an upstream value that has since changed
with nodes as (
    select * from {{ ref('graph_nodes') }}
),

-- The metals our ore classes are smelted to, by their MRDS commodity name.
metals as (
    select * from (values ('copper'), ('iron'), ('tin')) as metals(commodity)
),

-- Ore names already decided: matched to a curated source kind, or reviewed in the ore crosswalk (taken or rejected).
reviewed as (
    select lower(mrds_ore) as name from {{ source('raw', 'ore_minerals') }}
    union
    select lower(value) from {{ source('raw', 'mrds_sources') }} where field = 'ore'
),

listings as (
    select deposits.record_id, unnest(deposits.ore_minerals) as ore, deposits.commodities
    from {{ ref('stg_mrds__deposits') }} as deposits
),

ore_candidates as (
    select
        'ore_candidate' as kind,
        lower(listings.ore) as subject,
        min(listings.ore) as label,
        'Listed as an ore mineral on ' || count(distinct listings.record_id) || ' MRDS deposits of '
            || string_agg(distinct metals.commodity, ', ' order by metals.commodity)
            || '. Review it in data/crosswalks/ore_minerals.csv: an ore class, or none.' as detail,
        count(distinct listings.record_id) as priority,
        json_object('deposits', count(distinct listings.record_id),
                    'metals', list_sort(list(distinct metals.commodity))) as evidence
    from listings
    join metals on list_contains(list_transform(listings.commodities, lambda c: lower(c)), metals.commodity)
    where lower(listings.ore) not in (select name from reviewed)
    group by lower(listings.ore)
    -- Fewer than this is too thin to be worth a review yet.
    having count(distinct listings.record_id) >= 20
),

achieved as (
    select distinct document -> 'achieves' ->> 'thing' as thing from nodes where node_type = 'route'
),

extracted_without_route as (
    select 'extracted_without_route', id, label,
        'Extracted, but no route extracts it: add one from its source.', null::bigint, json_object()
    from nodes
    where kind = 'material' and document ->> 'origin' = 'extracted' and id not in (select thing from achieved where thing is not null)
),

placed as (
    select distinct source_id from {{ ref('source_occurrences') }} where source_id is not null
),

sources_without_places as (
    select 'source_without_places', id, label,
        'No mapped places: extend a crosswalk to an upstream dataset, or leave it to its curated regions.',
        null::bigint, json_object('regions', document -> 'regions')
    from nodes
    where kind = 'source' and document ->> 'availability' is distinct from 'ubiquitous'
        and id not in (select source_id from placed)
),

routes_unverified as (
    select 'route_unverified', id, label,
        'Every reference is unverified: read one and confirm what it supports.',
        null::bigint, json_object('references', json_array_length(coalesce(document -> 'references', '[]')))
    from nodes
    where node_type = 'route'
        and not exists (
            select 1 from json_each(coalesce(nodes.document -> 'references', '[]')) as reference
            where reference.value ->> 'status' in ('secondary', 'verified')
        )
),

facts as (
    select * from {{ ref('graph_facts') }}
),

disagreements as (
    select 'upstream_disagreement', id, id,
        'The curated value differs from upstream''s: remove it, or override upstream with a reason and a reference.',
        null::bigint, json_object('curated', curated_value, 'upstream', upstream_value)
    from facts where disagrees
),

stale_overrides as (
    select 'stale_override', id, id,
        'Upstream has changed since this override was written: check it still holds.',
        null::bigint, json_object('replaces', override -> 'replaces', 'upstream', upstream_value)
    from facts where (override ->> 'stale')::boolean
),

queue as (
    select * from ore_candidates
    union all select * from extracted_without_route
    union all select * from sources_without_places
    union all select * from routes_unverified
    union all select * from disagreements
    union all select * from stale_overrides
)

select
    kind || '/' || subject as id,
    kind,
    subject,
    label,
    detail,
    priority,
    evidence
from queue
order by kind, priority desc nulls last, subject
