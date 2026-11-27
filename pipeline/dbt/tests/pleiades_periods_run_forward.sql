-- A Pleiades period's years run forward and are signed years (ADR 0051): no year 0, which signed years don't have. A
-- period that broke this would date places wrongly, so it stops the build rather than be read.
select key, from_year, to_year
from {{ ref('stg_pleiades__periods') }}
where from_year > to_year or from_year = 0 or to_year = 0
    -- One year without the other: the parser read text that isn't a whole number.
    or (from_year is null) <> (to_year is null)
