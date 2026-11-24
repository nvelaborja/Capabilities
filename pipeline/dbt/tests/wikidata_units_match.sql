-- A Wikidata value in a unit other than the one our quantity expects would be read as ours unconverted (kg/m³ as
-- g/cm³), so it fails the build instead. Fix it with a conversion, or by suppressing the item.
select statements.record_id, statements.property, statements.unit, properties.unit as expected_unit
from {{ ref('stg_wikidata__quantities') }} as statements
join {{ ref('stg_curated__quantity_properties') }} as properties on properties.property = statements.property
where statements.unit is distinct from properties.unit
