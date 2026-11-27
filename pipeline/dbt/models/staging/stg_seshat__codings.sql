-- Seshat's codings (ADR 0053), typed: one row per coding of a polity, with the polity's years and, when a coding covers
-- only part of them, its own. Years are signed, negative BCE (ADR 0051); Seshat ends one polity in year 0, as Cliopatria
-- does the range before AD 1, so an ending 0 is read as 1 BCE and a starting 0 as AD 1 (ADR 0052). A coding of no polity
-- says nothing about one, and is left out.
with codings as (
    select * from {{ source('raw', 'seshat_codings') }}
    where polity_name <> ''
)

select
    record_id,
    variable,
    polity_id::integer as polity_id,
    polity_name,
    polity_long_name,
    case polity_start_year::integer when 0 then 1 else polity_start_year::integer end as polity_from_year,
    case polity_end_year::integer when 0 then -1 else polity_end_year::integer end as polity_to_year,
    case try_cast(year_from as integer) when 0 then 1 else try_cast(year_from as integer) end as year_from,
    case try_cast(year_to as integer) when 0 then -1 else try_cast(year_to as integer) end as year_to,
    value,
    tag,
    is_disputed = 'True' as is_disputed,
    is_uncertain = 'True' as is_uncertain,
    description
from codings
