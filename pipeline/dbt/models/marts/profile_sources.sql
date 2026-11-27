-- Which sources each profile had, from the map (ADR 0052): one row per profile and source kind found inside its area.
-- yes: an occurrence inside was worked by the profile's last year. maybe: occurrences are inside, but none is known to
-- have been worked by then ("present, not known to be worked by then"); never assumed. A source with nothing inside has
-- no row: it isn't in the area. A source kind can be an ore class, when a Pleiades mine doesn't say which ore it was.
with inside as (
    select inside.profile_id, inside.worked_by_then, occurrences.*
    from {{ ref('profile_occurrences') }} as inside
    join {{ ref('source_occurrences') }} as occurrences on occurrences.id = inside.occurrence_id
),

kinds as (
    select id, kind from {{ ref('graph_nodes') }}
)

select
    inside.profile_id || '/' || inside.source_id as id,
    inside.profile_id,
    inside.source_id,
    kinds.kind as source_kind,
    case when bool_or(inside.worked_by_then) then 'yes' else 'maybe' end as availability,
    count(*) filter (where inside.worked_by_then) as worked_by_then,
    count(*) filter (where not inside.worked_by_then) as not_known_worked,
    -- A few to show: the earliest worked first, then the rest by their year (if any) and name.
    list(
        {'id': inside.id, 'name': inside.name, 'dataset': inside.dataset, 'worked_by_year': inside.worked_by_year}
        order by inside.worked_by_then desc, inside.worked_by_year nulls last, inside.name, inside.id
    )[1:5] as examples
from inside
left join kinds on kinds.id = inside.source_id
group by inside.profile_id, inside.source_id, kinds.kind
order by inside.profile_id, inside.source_id
