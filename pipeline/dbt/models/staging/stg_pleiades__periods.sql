-- Pleiades' time periods with their years (ADR 0051): signed years, negative BCE, no year 0, as Pleiades writes them.
select
    key,
    label,
    try_cast(from_year as integer) as from_year,
    try_cast(to_year as integer) as to_year
from {{ source('raw', 'pleiades_periods') }}
