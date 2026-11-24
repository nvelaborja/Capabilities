-- The works OpenAlex and Crossref returned for each citation (ADR 0047), typed, with each title reduced to its words
-- for comparing. A lookup that found nothing is a row with no candidate (rank null).
select
    citation,
    service,
    lookup,
    query,
    status,
    try_cast(rank as integer) as rank,
    record_id,
    lower(doi) as doi,
    title,
    try_cast(year as integer) as year,
    authors,
    type,
    oa_url,
    pdf_url,
    try_cast(score as double) as score,
    {{ title_words('title') }} as title_words,
    {{ title_words("split_part(title, ':', 1)") }} as main_title_words,
    {{ plain_text('authors') }} as plain_authors
from {{ source('raw', 'reference_candidates') }}
where service <> 'link'
