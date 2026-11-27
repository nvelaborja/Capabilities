-- A curated working date names a record that is an occurrence (ADR 0051). One that names nothing does nothing: a typo,
-- or a record the dataset no longer has or the curated layer suppresses. A warning, so a refreshed download that drops a
-- record doesn't stop the build.
{{ config(severity='warn') }}
select dates.id, dates.dataset, dates.record_id
from {{ ref('stg_curated__dates') }} as dates
left join {{ ref('source_occurrences') }} as occurrences
    on occurrences.dataset = dates.dataset and occurrences.record_id = dates.record_id
where occurrences.id is null
