-- Open reports from readers (ADR 0050): one row per GitHub issue, with the fact the app's link named. An issue opened
-- without the app's link may name no fact; it still needs reading.
select
    cast(number as integer) as number,
    url,
    title,
    cast(created_at as timestamptz) as created_at,
    nullif(trim(fact), '') as fact,
    nullif(trim(kind), '') as fact_kind,
    nullif(trim(reference), '') as reference,
    nullif(trim(run), '') as run
from {{ source('raw', 'github_reports') }}
