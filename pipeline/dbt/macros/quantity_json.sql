{#- A quantity value as the curated layer writes it: one number when low equals high, otherwise [low, high]. Whole
    numbers are written as integers, so an upstream 3.0 reads like a curated 3. -#}
{% macro quantity_number(x) -%}
    case when {{ x }} = floor({{ x }}) then to_json({{ x }}::bigint) else to_json({{ x }}) end
{%- endmacro %}

{% macro quantity_json(low, high) -%}
    case
        when {{ low }} is null then null
        when {{ low }} = {{ high }} then {{ quantity_number(low) }}
        else json_array({{ quantity_number(low) }}, {{ quantity_number(high) }})
    end
{%- endmacro %}

{#- The low and high ends of a curated quantity value (a number or a [low, high] array). -#}
{% macro quantity_low(value) -%}
    case json_type({{ value }}) when 'ARRAY' then ({{ value }} ->> 0)::double else ({{ value }} ->> '$')::double end
{%- endmacro %}

{% macro quantity_high(value) -%}
    case json_type({{ value }}) when 'ARRAY' then ({{ value }} ->> 1)::double else ({{ value }} ->> '$')::double end
{%- endmacro %}
