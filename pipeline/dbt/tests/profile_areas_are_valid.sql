-- Every profile's area is a valid polygon, so that what is inside it is well defined.
select id
from {{ ref('profile_areas') }}
where not st_isvalid(geometry::geometry) or st_isempty(geometry::geometry)
