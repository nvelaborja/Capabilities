-- Where and when each profile is (ADR 0052): the Cliopatria entity it names, and its years, signed (ADR 0051). Profiles
-- without a place are hand-picked lists only, and have no row.
select
    id,
    document -> 'place' ->> 'cliopatria' as cliopatria,
    (document -> 'years' ->> 0)::integer as from_year,
    (document -> 'years' ->> 1)::integer as to_year,
    path
from {{ ref('stg_curated__documents') }}
where node_type = 'profile' and (document -> 'place') is not null
