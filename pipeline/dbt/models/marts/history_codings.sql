-- What Seshat says each generated profile's polity had (ADR 0053): one row per polity and variable the crosswalk compares.
-- A polity coded present in any of its years had it; else absent if coded so; else unknown (unknown, uncoded, or a
-- coding missing). Kept in the build and never written to data/: Seshat's data is CC BY-SA 4.0.
with profiles as (
    select id, seshat_polity from {{ ref('profile_areas') }} where origin = 'seshat'
),

codings as (
    select * from {{ ref('stg_seshat__codings') }}
),

variables as (
    select variable, compares, nullif(thing, '') as thing from {{ source('raw', 'seshat_variables') }}
)

select
    profiles.id || '/' || variables.variable as id,
    profiles.id as profile_id,
    any_value(codings.polity_id) as polity_id,
    profiles.seshat_polity,
    any_value(codings.polity_long_name) as polity_long_name,
    variables.variable,
    variables.compares,
    variables.thing,
    case
        when bool_or(codings.value = 'present') then 'present'
        when bool_or(codings.value = 'absent') then 'absent'
        else 'unknown'
    end as history,
    -- How sure Seshat is of the polity's codings of the variable, all of them, not only those that decided it: confident
    -- (TRS), suspected (SSP), inferred (IFR), undecided (UND).
    list_sort(list(distinct codings.tag) filter (where codings.tag is not null)) as tags,
    coalesce(bool_or(codings.is_disputed), false) as disputed,
    list_sort(list(codings.record_id) filter (where codings.record_id is not null)) as records
from profiles
cross join variables
left join codings on codings.polity_name = profiles.seshat_polity and codings.variable = variables.variable
group by profiles.id, profiles.seshat_polity, variables.variable, variables.compares, variables.thing
order by profiles.id, variables.variable
