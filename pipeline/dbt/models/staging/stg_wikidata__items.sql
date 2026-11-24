-- Each Wikidata item's English label and description, and its chemical formula: one row per item. An item with
-- several formulas keeps the first in order, so the choice is the same on every build.
select
    item as record_id,
    any_value(label) as label,
    any_value(description) as description,
    min(formula) as formula
from {{ source('raw', 'wikidata_items') }}
group by item
