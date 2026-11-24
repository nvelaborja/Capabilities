-- Wikidata quantity statements with typed values: one row per statement (ADR 0043). A statement without bounds is a
-- single value, so its low and high are its amount.
select
    item as record_id,
    property,
    try_cast(amount as double) as amount,
    try_cast(coalesce(lower, amount) as double) as low,
    try_cast(coalesce(upper, amount) as double) as high,
    unit
from {{ source('raw', 'wikidata_quantities') }}
