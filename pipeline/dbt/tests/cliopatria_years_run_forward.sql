-- Every Cliopatria row's years run forward and are signed years, with no year 0 (ADR 0051), once staging has read
-- Cliopatria's year 0: a profile's years are compared with them.
select name, from_year, to_year
from {{ ref('stg_cliopatria__polities') }}
where from_year is null or to_year is null or from_year > to_year or from_year = 0 or to_year = 0
