-- Every occurrence is a valid point on the globe.
select id, latitude, longitude
from {{ ref('source_occurrences') }}
-- The cast is for an empty build: DuckDB writes no GeoParquet metadata for a file with no rows, so the column reads
-- back as WKB bytes rather than as a geometry.
where not st_isvalid(geometry::geometry)
    or latitude not between -90 and 90
    or longitude not between -180 and 180
