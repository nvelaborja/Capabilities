# DuckDB spatial and GeoParquet

## What it is

**DuckDB's spatial extension** adds a `GEOMETRY` type and over 150 `ST_` functions to [DuckDB](duckdb.md): making points and shapes, measuring them, testing whether one contains another, and reading and writing geospatial file formats. It is the same family of functions as PostGIS, the spatial extension of Postgres, but it runs in process with no server.

**GeoParquet** is a convention for storing geometries in [Parquet](parquet.md) files. A geometry column holds each shape as bytes in a standard encoding, and a `geo` entry in the file's metadata says which column holds geometries, how they are encoded, which coordinate system they use, and their bounding box. Any GeoParquet reader (DuckDB, GeoPandas, QGIS, GDAL) then knows the column is a geometry and not just bytes.

## How it works

**Simple Features.** Most geospatial software uses the same model of geometries, an OGC and ISO standard called *Simple Features*: `POINT`, `LINESTRING`, `POLYGON`, and `MULTI...` collections of each. A point is a pair of coordinates; a polygon is a closed ring of them, possibly with holes.

**Two encodings.** *Well-known text* (WKT) is the readable one: `POINT (-106.26 39.24)`. *Well-known binary* (WKB) is the compact one that files store. `ST_AsText(geometry)` turns a geometry into WKT, `ST_GeomFromWKB(bytes)` makes one from WKB, and `ST_Point(x, y)` makes a point from two numbers.

**x is longitude.** Coordinates are (x, y), and in geographic coordinates x is longitude (east–west) and y is latitude. It's the opposite of how people usually say a place's position ("39.24° N, 106.26° W"). So it is `ST_Point(longitude, latitude)`. Getting it backwards moves places to the wrong part of the world, or to latitudes that don't exist.

**Coordinate reference systems (CRS).** Numbers only mean a place given a CRS. The one GPS uses is WGS 84: longitude and latitude in degrees. `EPSG:4326` and `OGC:CRS84` both name it. The difference is that 4326 officially lists latitude first, and CRS84 longitude first, which is the order files and software actually use. GeoParquet's default is CRS84. Distances in degrees are not distances on the ground, so measuring needs a projected CRS or functions that work on the sphere, such as `ST_Distance_Sphere`.

**Predicates and the engine underneath.** `ST_Contains(area, point)`, `ST_Intersects`, `ST_DWithin(a, b, distance)` and their kin answer spatial questions; `ST_IsValid` checks that a geometry follows the rules (a polygon that crosses itself is invalid). Under the hood the extension uses established C/C++ libraries, linked into the extension:

- GEOS, for geometry operations;
- PROJ, for transforming between coordinate systems;
- GDAL, for reading and writing other formats (Shapefile, GeoJSON, GeoPackage) through `ST_Read`.

**GeoParquet metadata.** With the extension loaded, `copy ... to 'file.parquet'` writes a geometry column as WKB and adds the `geo` metadata. Reading the file back gives a `GEOMETRY` column again. `parquet_kv_metadata('file.parquet')` shows the metadata. Bounding boxes let readers skip files, or parts of files, that are nowhere near the area they ask about.

**Loading the extension.** `install spatial` downloads it from DuckDB's extension repository into `~/.duckdb/extensions`, once per DuckDB version; `load spatial` loads it into a connection. dbt-duckdb does both when a profile lists `extensions: [spatial]`.

## How we use it

- **Making occurrences.** The `source_occurrences` mart turns each matched MRDS deposit's longitude and latitude into `ST_Point(longitude, latitude)` ([data pipeline](../data-pipeline.md), [ADR 0041](../../adr/0041-place-sources-with-mrds-deposits-through-a-crosswalk.md)).
- **Checking them.** The `occurrences_are_valid_points` test fails the build if any geometry is invalid or out of range.
- **Publishing them.** dbt-duckdb writes the mart to `build/graph/source_occurrences.parquet`. With the extension loaded, that is a GeoParquet file with CRS84 points and a bounding box, so any GIS tool can open it.
- **Next.** The occurrences API and map (M1) read this file. In M4, profile areas (polygons) and polity borders will use `ST_Contains` to work out which occurrences lie inside a profile ([ADR 0036](../../adr/0036-place-sources-and-profiles-in-space-and-time.md)).

Why: [ADR 0036](../../adr/0036-place-sources-and-profiles-in-space-and-time.md) chose DuckDB spatial so that spatial work stays in the same engine and the same dbt project, with no PostGIS server. GeoParquet is the open format the rest of the geospatial world reads. In M5 the same data moves to Iceberg tables ([ADR 0036](../../adr/0036-place-sources-and-profiles-in-space-and-time.md) allows GeoParquet or Iceberg geometry columns).

## Where it lives

| What | Where |
|---|---|
| Loading the extension for dbt | `pipeline/dbt/profiles.yml` (`extensions: [spatial]`) |
| Making the points | `pipeline/dbt/models/marts/source_occurrences.sql` |
| The geometry test | `pipeline/dbt/tests/occurrences_are_valid_points.sql` |
| The output | `build/graph/source_occurrences.parquet` (generated) |
| Tests that read it back | `pipeline/tests/test_upstream.py` |

```python
import duckdb
con = duckdb.connect()
con.execute("load spatial")
con.sql("""
    select source_id, name, st_astext(geometry::geometry) as point
    from 'build/graph/source_occurrences.parquet'
    where id is not null and source_id = 'tin-gravel'
    limit 5
""").show()
con.sql("select * from parquet_kv_metadata('build/graph/source_occurrences.parquet')").show()
```

## Things to know

- **The first build on a new machine downloads the extension** (a one-time network call, then cached). If it can't, the build fails at the first spatial function.
- **An empty file has no GeoParquet metadata.** DuckDB writes `geo` metadata only when there are rows, so with no MRDS snapshot `geometry` reads back as plain WKB bytes. Cast it, `geometry::geometry`, before using `ST_` functions; the cast also works on a real geometry. Skip the row of nulls that dbt-duckdb writes for an empty model (`where id is not null`).
- **Longitude first**, always: `ST_Point(longitude, latitude)`.
- **Degrees aren't distances.** Don't compare `ST_Distance` results on CRS84 points with kilometres.
- Our `longitude` and `latitude` columns duplicate the point, so readers without a spatial library (the web app's JSON, a quick query) don't need one.

## Further reading

1. [Spatial extension overview](https://duckdb.org/docs/stable/core_extensions/spatial/overview) and its [function reference](https://duckdb.org/docs/stable/core_extensions/spatial/functions) (DuckDB docs).
2. [PostGEESE? Introducing the DuckDB Spatial Extension](https://duckdb.org/2023/04/28/spatial) (DuckDB blog): what it does and how it is built.
3. [GeoParquet](https://geoparquet.org/), and the [specification](https://github.com/opengeospatial/geoparquet/blob/main/format-specs/geoparquet.md): the `geo` metadata in detail.
4. [Simple Features](https://en.wikipedia.org/wiki/Simple_Features) and [well-known text and binary](https://en.wikipedia.org/wiki/Well-known_text_representation_of_geometry) (Wikipedia).
5. [World Geodetic System (WGS 84)](https://en.wikipedia.org/wiki/World_Geodetic_System) (Wikipedia) and [EPSG:4326](https://epsg.io/4326).
6. The libraries underneath: [GEOS](https://libgeos.org/), [PROJ](https://proj.org/) and [GDAL](https://gdal.org/).
