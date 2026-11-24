-- Every work the graph cites, checked against OpenAlex and Crossref (build/graph/reference_checks.parquet, ADR 0047):
-- one row per work, with the best candidate found for it, how sure the match is, a free copy where OpenAlex knows one,
-- and whether each link cited for it still loads. A check never changes a reference's status: a person reads the work.
--
-- result:
--   found            the work itself: a candidate with the cited title (most of its words), first author and year
--                    (give or take one)
--   review_found     only a review of it: the work exists, but neither service lists it itself (common for books)
--   possible         a candidate close in some of those but not all: a person should look
--   not_found        nothing close. Many books and reports are in neither; that doesn't make the work doubtful
--   doi_disagrees    the DOI cited leads to a different work
--   not_searched     a web page or a work with no year: only its links are checked
--   not_checked_yet  cited since the candidates were last downloaded
with uses as (
    select * from {{ ref('stg_references__cited') }}
),

works as (
    select
        citation,
        max(doi) as doi,
        list_sort(list(distinct url) filter (where url is not null)) as urls,
        -- Copied routes follow their template, where the work is read (stg_references__cited).
        list_sort(list(distinct status) filter (where not copied)) as statuses,
        coalesce(bool_and(status = 'verified') filter (where not copied), false) as verified,
        list_sort(list(distinct node_id)) as cited_by,
        count(distinct node_id) filter (where node_type = 'route') as routes
    from uses
    group by citation
),

-- What the citation itself says, read the way the download reads it (citations.py): the year in brackets, the title
-- after it up to the first full stop, and the first author's surname at the start.
cited as (
    select
        *,
        doi is not null or regexp_matches(citation, '\(\d{4}\)') as searchable,
        try_cast(regexp_extract(citation, '\((\d{4})\)', 1) as integer) as cited_year,
        {{ plain_text("regexp_extract(citation, '^([^,(.]+)', 1)") }} as cited_surname,
        coalesce(nullif(regexp_replace(trim(split_part(
            regexp_extract(citation, '\(\d{4}\)[.:,]?\s*(.*)$', 1), '. ', 1), ' .''"‘’“”'),
            '(,\s*\d+(st|nd|rd|th) ed\.?|,\s+as summari[sz]ed in .*)$', ''), ''),
            regexp_extract(citation, '^(.*?)\s*\(\d{4}\)', 1)) as cited_title
    from works
),

scored as (
    select
        cited.citation,
        candidates.*  exclude (citation),
        greatest(
            {{ word_overlap('candidates.title_words', title_words('cited.cited_title')) }},
            {{ word_overlap('candidates.main_title_words', title_words("split_part(cited.cited_title, ':', 1)")) }}
        ) as title_score,
        -- Unknown (null) when the candidate lists no authors, which is common for books.
        case when candidates.plain_authors <> '' then
            -- A whole word: Fall isn't Fallon. Both are plain text, so the surname is safe in a pattern.
            cited.cited_surname <> ''
                and regexp_matches(candidates.plain_authors, '\b' || cited.cited_surname || '\b') end as author_matches,
        abs(candidates.year - cited.cited_year) <= 1 as year_matches,
        coalesce(candidates.type in ('book-review', 'review', 'peer-review'), false) as is_review,
        cited.cited_year
    from cited
    join {{ ref('stg_references__candidates') }} as candidates on candidates.citation = cited.citation
    where candidates.rank is not null
),

judged as (
    select
        *,
        case
            when title_score >= 0.8 and not is_review and author_matches and coalesce(year_matches, true) then 'found'
            -- A review comes out in the years after the work.
            when title_score >= 0.8 and is_review and year between cited_year and cited_year + 5 then 'review_found'
            when title_score >= 0.5 then 'possible'
        end as verdict
    from scored
),

best as (
    select * from judged
    qualify row_number() over (
        partition by citation
        order by verdict is null, verdict = 'possible', verdict = 'review_found', title_score desc,
            abs(year - cited_year) nulls last,
            service = 'crossref', rank
    ) = 1
),

-- A free copy: OpenAlex's, for the work found or the same DOI. Not for a review or a possible match: a copy of those
-- may not be the work.
free_copies as (
    select best.citation, any_value(coalesce(openalex.pdf_url, openalex.oa_url)) as free_copy
    from best
    join judged as openalex on openalex.citation = best.citation and openalex.service = 'openalex'
        and (openalex.record_id = best.record_id or openalex.doi = best.doi)
        and coalesce(openalex.pdf_url, openalex.oa_url) is not null
    where best.verdict = 'found'
    group by best.citation
),

-- Looked up the way it is cited now: by its DOI, or by searching when it has none. A DOI added or changed since the
-- download makes the work not checked yet, rather than keep the old answer.
looked_up as (
    select distinct candidates.citation
    from {{ ref('stg_references__candidates') }} as candidates
    join works on works.citation = candidates.citation
    where (works.doi is null and candidates.lookup = 'search')
        or (candidates.lookup = 'doi' and lower(candidates.query) = lower(works.doi))
),

links as (
    select
        query as url,
        status,
        case
            when regexp_matches(status, '^[23]\d\d$') then 'works'
            -- Some sites turn away anything that isn't a browser; the link may well work.
            when status in ('401', '403', '429') then 'refused'
            else 'broken'
        end as state
    from {{ source('raw', 'reference_candidates') }}
    where service = 'link'
),

checked_links as (
    select
        cited.citation,
        to_json(list(struct_pack(url := urls.url, status := links.status, state := links.state) order by urls.url)) as links
    from cited, unnest(cited.urls) as urls(url)
    left join links on links.url = urls.url
    group by cited.citation
),

snapshot as (
    select retrieved_at from {{ source('raw', 'upstream_snapshots') }} where dataset = 'reference_candidates'
),

checks as (
    select
        cited.*,
        best.verdict,
        best.lookup,
        best.service as match_service,
        best.record_id as match_id,
        best.doi as match_doi,
        best.title as match_title,
        best.year as match_year,
        best.authors as match_authors,
        best.type as match_type,
        best.title_score,
        best.author_matches,
        best.year_matches,
        best.is_review,
        cited.citation in (select citation from looked_up) as was_looked_up
    from cited
    left join best on best.citation = cited.citation
),

results as (
    select
        *,
        case
            when not searchable then 'not_searched'
            when not was_looked_up then 'not_checked_yet'
            when doi is not null and lookup = 'doi' and verdict is null then 'doi_disagrees'
            when verdict is not null then verdict
            else 'not_found'
        end as result
    from checks
),

-- The record a work was matched to, when there is one worth showing: the work, a review of it, a possible match, or the
-- work a wrong DOI leads to.
shown as (
    select *, result in ('found', 'review_found', 'possible', 'doi_disagrees') as has_match from results
)

select
    'ref-' || left(md5(results.citation), 12) as id,
    results.citation,
    results.doi,
    results.statuses,
    results.verified,
    results.cited_by,
    results.routes,
    results.result,
    case results.result
        when 'possible' then concat_ws('; ',
            case when results.title_score < 0.8 then 'the title differs' end,
            case when results.author_matches is null then 'it lists no authors' end,
            case when not results.author_matches then 'the first author isn''t among its authors' end,
            case when results.is_review then 'it is a review' end,
            case when not results.year_matches then 'the year differs (cited ' || results.cited_year || ', found '
                || results.match_year || ')'
                || case when results.title_score >= 0.8 then ': perhaps another edition' else '' end
            end)
        when 'review_found' then 'Only a review of it was found: the work exists, though neither OpenAlex nor Crossref '
            || 'lists it itself.'
        when 'not_found' then 'Nothing close in OpenAlex or Crossref. Many books and reports are in neither; that '
            || 'doesn''t make the work doubtful.'
        when 'doi_disagrees' then 'The DOI cited leads to a different work.'
        when 'not_searched' then 'A web page, or a work with no year: only its links are checked.'
        when 'not_checked_yet' then 'Cited since the works were last looked up.'
    end as note,
    case when results.has_match then results.match_service end as match_service,
    case when results.has_match then results.match_id end as match_id,
    case when results.has_match then results.match_doi end as match_doi,
    case when results.has_match then results.match_title end as match_title,
    case when results.has_match then results.match_year end as match_year,
    case when results.has_match then results.match_authors end as match_authors,
    case when results.has_match then results.match_type end as match_type,
    round(results.title_score, 2) as title_score,
    free_copies.free_copy,
    coalesce(checked_links.links, '[]'::json) as links,
    (select retrieved_at from snapshot) as checked_at
from shown as results
left join free_copies on free_copies.citation = results.citation
left join checked_links on checked_links.citation = results.citation
order by results.citation
