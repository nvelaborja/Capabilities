-- The curation queue (ADR 0034, ADR 0045): the gaps the build finds, as a to-do list for people and, from M3, agents.
-- One row per item, most valuable first within each kind:
--   reported                  a fact readers reported as wrong on GitHub, one item per fact. First: a report is someone
--                             telling us the graph is wrong (ADR 0050)
--   ore_candidate             a mineral MRDS lists as an ore on many copper, iron or tin deposits, not yet reviewed
--   extracted_without_route   a material said to be extracted that no route extracts
--   source_without_places     a regional source with no mapped places
--   route_unverified          a route whose references are all unchecked
--   upstream_disagreement     a curated value that differs from upstream's
--   stale_override            an override of an upstream value that has since changed
--   unread_reference          a work cited but not yet read and verified everywhere it is cited, ranked by how many
--                             routes depend on it, with a free copy where OpenAlex knows one (the reading queue, ADR 0047)
--   unmatched_place           Pleiades mines and quarries that name a material no rule matches, by material. Last:
--                             where a material was found matters least to the app's questions (ADR 0046)
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
    -- A quote an agent proposed (ADR 0049) doesn't verify anything, but it is where a person's reading starts.
    select 'route_unverified', id, label,
        case when exists (
            select 1 from json_each(coalesce(nodes.document -> 'references', '[]')) as reference
            where reference.value ->> 'quote' is not null
        )
        then 'A quote is ready to check: read it on its page, and mark the reference verified if it says what it supports.'
        else 'Every reference is unverified: read one and confirm what it supports.' end,
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

-- Mines and quarries with coordinates that no rule placed, counted by each material they name.
pleiades_placed as (
    select distinct record_id from {{ ref('source_occurrences') }} where dataset = 'pleiades'
),

unplaced_workings as (
    select
        record_id,
        case when len(materials) = 0 then [null] else materials end as materials
    from {{ ref('stg_pleiades__workings') }}
    where latitude is not null and longitude is not null
        and record_id not in (select record_id from pleiades_placed)
        -- A suppressed place was looked at and left out: it isn't a gap.
        and record_id not in (
            select record_id from {{ source('raw', 'suppressed_records') }} where dataset = 'pleiades'
        )
),

unmatched_places as (
    select
        'unmatched_place' as kind,
        'pleiades:' || coalesce(material, '(none)') as subject,
        coalesce(upper(left(material, 1)) || substr(material, 2), 'No material named') as label,
        count(*) || ' Pleiades mines and quarries '
            || coalesce('name ' || material || ' and match no rule', 'name no material')
            || '. If one of our sources is found there, add a rule to data/crosswalks/pleiades_sources.csv;'
            || ' otherwise leave them.' as detail,
        count(*) as priority,
        json_object('places', count(*)) as evidence
    from (select record_id, unnest(materials) as material from unplaced_workings)
    group by material
),

-- The reading queue: every work some use of which isn't verified, the most depended on first.
unread_references as (
    select
        'unread_reference' as kind,
        id as subject,
        citation as label,
        'Cited by ' || case
                when routes = 0 then len(cited_by) || ' node' || case when len(cited_by) = 1 then '' else 's' end
                else routes || ' route' || case when routes = 1 then '' else 's' end
                    || case when len(cited_by) > routes then ' and ' || (len(cited_by) - routes) || ' other node'
                        || case when len(cited_by) - routes = 1 then '' else 's' end else '' end
            end
            || '. ' || case result
                when 'found' then 'Found in ' || case match_service when 'openalex' then 'OpenAlex' else 'Crossref' end
                    || coalesce(', with a free copy: ' || free_copy, '') || '.'
                when 'review_found' then 'Only a review of it is in '
                    || case match_service when 'openalex' then 'OpenAlex' else 'Crossref' end || '.'
                when 'possible' then 'Possibly in ' || case match_service when 'openalex' then 'OpenAlex' else 'Crossref' end
                    || ' (' || note || ').'
                else note
            end
            || ' Read it, and mark the claims it supports verified.' as detail,
        routes as priority,
        json_object('result', result, 'free_copy', free_copy, 'doi', coalesce(doi, match_doi),
                    'statuses', statuses) as evidence
    from {{ ref('reference_checks') }}
    where not verified
),

-- Readers' reports, one item per fact: every open issue about it, oldest first. An issue that names no fact is an item
-- of its own.
reports as (
    select
        'reported' as kind,
        coalesce(reports.fact, '#' || min(reports.number)) as subject,
        coalesce(min(nodes.label), reports.fact, min(reports.title)) as label,
        'Reported in ' || string_agg('#' || reports.number || ' (' || reports.title || ')', ', '
            order by reports.number) || '. Read the report; if it holds, withdraw the fact with '
            || '`uv run capabilities withdraw` (an agent''s) or correct it (a person''s), and close the issue from the '
            || 'pull request.' as detail,
        count(*) as priority,
        json_object('issues', list(reports.url order by reports.number),
                    'runs', list_filter(list(distinct reports.run), lambda run: run is not null),
                    'references', list_filter(list(distinct reports.reference), lambda ref: ref is not null)) as evidence
    from {{ ref('stg_github__reports') }} as reports
    left join nodes on nodes.id = reports.fact
    group by reports.fact, case when reports.fact is null then reports.number end
),

queue as (
    select * from reports
    union all select * from ore_candidates
    union all select * from extracted_without_route
    union all select * from sources_without_places
    union all select * from routes_unverified
    union all select * from disagreements
    union all select * from stale_overrides
    union all select * from unread_references
    union all select * from unmatched_places
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
-- Reports first: someone told us the graph is wrong (ADR 0050). Unmatched places last: the app's questions don't
-- depend on where a material was found (ADR 0046).
order by kind <> 'reported', kind = 'unmatched_place', kind, priority desc nulls last, subject
