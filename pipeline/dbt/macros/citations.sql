-- Text reduced for comparing names and titles: no accents, no punctuation, lower case, single spaces.
{% macro plain_text(column) -%}
    trim(regexp_replace(lower(strip_accents(coalesce({{ column }}, ''))), '[^a-z0-9]+', ' ', 'g'))
{%- endmacro %}

-- The distinct words of a title, for comparing two titles whatever their punctuation or word order.
{% macro title_words(column) -%}
    list_distinct(list_filter(string_split({{ plain_text(column) }}, ' '), lambda w: w <> ''))
{%- endmacro %}

-- How alike two sets of words are: the words they share over the words either has (1 = the same words).
{% macro word_overlap(a, b) -%}
    coalesce(len(list_intersect({{ a }}, {{ b }}))::double / nullif(len(list_distinct(list_concat({{ a }}, {{ b }}))), 0), 0)
{%- endmacro %}
