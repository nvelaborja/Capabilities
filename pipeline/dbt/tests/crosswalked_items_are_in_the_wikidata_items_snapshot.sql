-- Every Wikidata item a crosswalk names is in the items snapshot. One that isn't was added to a crosswalk after the
-- last download: its node would be built with MRDS's name and no description or values from Wikidata, so the build
-- stops instead (ADR 0044). Download again (`dg launch --assets 'upstream/wikidata_items'`, and
-- 'upstream/wikidata_quantities'), then `uv run capabilities backup`.
select crosswalk.thing_id, crosswalk.record_id
from {{ ref('stg_crosswalk__wikidata_items') }} as crosswalk
where crosswalk.record_id not in (select record_id from {{ ref('stg_wikidata__items') }})
