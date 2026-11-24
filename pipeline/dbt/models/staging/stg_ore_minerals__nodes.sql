-- Upstream ore minerals as nodes of the graph (ADR 0045). Each row of the ore crosswalk becomes three documents:
--   * the mineral, a material in its ore class, named and described from Wikidata;
--   * its deposits, a source whose places are the MRDS deposits that list it as an ore mineral;
--   * a mining route, cloned from the curated route the row names (`mined_like`), with the mineral and its deposit in
--     place of the template's. The template's references are kept, unverified and saying they were cited for the
--     template, since what they support is about its mineral, not this one.
-- So a mineral reaches whatever its class reaches (copper ore is smelted to copper), and is mined as its kind of ore is.
with ores as (
    select
        ores.*,
        -- Wikidata labels are lower case ("azurite"); MRDS's name is the fallback when Wikidata has no label.
        coalesce(upper(left(items.label, 1)) || substr(items.label, 2), ores.mrds_ore) as label,
        items.description as wikidata_description,
        items.formula
    from {{ source('raw', 'ore_minerals') }} as ores
    left join {{ ref('stg_wikidata__items') }} as items on items.record_id = ores.wikidata
    where ores.class <> 'none'
),

documents as (
    select * from {{ ref('stg_curated__documents') }}
),

-- The template route, the material it mines and the source it consumes.
templates as (
    select
        routes.id as template_id,
        routes.document as template,
        routes.document ->> 'label' as template_label,
        routes.document -> 'achieves' ->> 'thing' as template_material,
        materials.label as template_material_label,
        (
            select requirement.value ->> 'thing'
            from json_each(routes.document -> 'requires') as requirement
            where requirement.value ->> 'thing' in (select id from documents where kind = 'source')
        ) as template_source
    from documents as routes
    join documents as materials on materials.id = routes.document -> 'achieves' ->> 'thing'
    where routes.node_type = 'route'
),

reference as (
    select id, json_array(json_object(
        'citation', citation, 'url', url, 'supports', supports, 'status', 'unverified'
    )) as "references"
    from ores
),

-- Where each node came from: the mineral from its Wikidata item, its deposits' places from MRDS, and its route from
-- the template it copies.
provenance as (
    select id as mineral, 1 as part, json_object(
        'layer', 'upstream', 'dataset', 'wikidata', 'record', wikidata,
        'url', 'https://www.wikidata.org/wiki/' || wikidata, 'crosswalk', 'data/crosswalks/ore_minerals.csv'
    ) as provenance
    from ores
    union all
    select id, 2, json_object(
        'layer', 'upstream', 'dataset', 'mrds', 'record', 'deposits listing ' || mrds_ore || ' as an ore mineral',
        'crosswalk', 'data/crosswalks/ore_minerals.csv'
    )
    from ores
    union all
    select id, 3, json_object(
        'layer', 'upstream', 'copied_from', mined_like, 'crosswalk', 'data/crosswalks/ore_minerals.csv'
    )
    from ores
),

materials as (
    select
        1 as part,
        ores.id as mineral,
        'thing' as node_type,
        ores.id,
        json_object(
            'id', ores.id,
            'kind', 'material',
            'label', ores.label,
            'origin', 'extracted',
            'is_a', json_array(ores.class),
            'description', concat_ws(' ',
                upper(left(ores.wikidata_description, 1)) || substr(ores.wikidata_description, 2) || '.',
                case when ores.formula is not null then 'Formula ' || ores.formula || '.' end,
                ores.notes
            ),
            'references', reference."references"
        ) as document
    from ores
    join reference using (id)
),

sources as (
    select
        2 as part,
        ores.id as mineral,
        'thing' as node_type,
        ores.id || '-deposit' as id,
        json_object(
            'id', ores.id || '-deposit',
            'kind', 'source',
            'label', ores.label || ' deposit',
            'availability', 'regional',
            'description', 'Where ' || lower(ores.label) || ' is found: the MRDS deposits that list it as an ore mineral.'
        ) as document
    from ores
),

routes as (
    select
        3 as part,
        ores.id as mineral,
        'route' as node_type,
        'mine-' || ores.id as id,
        json_merge_patch(
            templates.template,
            json_object(
                'id', 'mine-' || ores.id,
                'label', replace(templates.template ->> 'label', lower(templates.template_material_label), lower(ores.label)),
                'achieves', json_object('thing', ores.id),
                'requires', replace(
                    (templates.template -> 'requires')::varchar,
                    '"' || templates.template_source || '"',
                    '"' || ores.id || '-deposit"'
                )::json,
                'outputs', json_array(json_object('thing', ores.id)),
                'references', (
                    select to_json(list(json_merge_patch(reference.value, json_object(
                        'status', 'unverified',
                        'supports', 'Cited for the route this copies (' || templates.template_label || '): '
                            || (reference.value ->> 'supports')
                    )) order by reference.key::integer))
                    from json_each(templates.template -> 'references') as reference
                )
            )
        ) as document
    from ores
    join templates on templates.template_id = ores.mined_like
)

select
    nodes.node_type,
    nodes.id,
    nodes.document ->> 'kind' as kind,
    nodes.document ->> 'label' as label,
    nodes.document,
    provenance.provenance,
    -- After every curated node, mineral by mineral, so the order is the same on every build.
    row_number() over (order by nodes.mineral, nodes.part) as position
from (select * from materials union all select * from sources union all select * from routes) as nodes
join provenance using (mineral, part)
