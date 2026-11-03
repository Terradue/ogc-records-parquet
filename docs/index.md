# ogc-records-parquet

Store PySTAC `OGCRecord` objects in Arrow and GeoParquet, with typed columns
for queries and a serialized document for reconstruction. Records may have
null geometry and need not have a STAC temporal extent.

The package uses
[pystac-ext-ogc-record](https://terradue.github.io/pystac-ext-ogc-record/)
for record parsing and serialization. It requires Python 3.11 or newer;
the repository test matrix covers Python 3.11–3.15.

## Choose your starting point

This documentation follows [Diátaxis](https://diataxis.fr/), with four
sections serving different needs.

| Your goal | Start here |
| --- | --- |
| Learn by writing and reading a small file | [Tutorial: your first round trip](tutorials/first-round-trip.md) |
| Accomplish a specific task | [Project and filter records](how-to/project-filter.md), [store memberships](how-to/collections.md), or [import and export](how-to/import-export.md) |
| Look up a contract or signature | [Python API](reference/api.md), [storage format](reference/storage-format.md), and [limitations](reference/limitations.md) |
| Understand the design | [Preservation and projections](explanation/preservation.md) and [OGC Records and STAC](explanation/ogc-and-stac.md) |

For existing applications, see [migration](how-to/migrate.md).
For local checks and documentation commands, see
[development](how-to/develop.md).

## Scope

The library converts records and stores local Parquet files. Query execution,
OGC profile validation, reprojection, and application-specific metadata mapping
belong to the calling application.

The project is licensed under Apache-2.0. The repository's `LICENSE` and
`NOTICE`, also included in built distributions, contain the license and
the acknowledgment of `stac-geoparquet`.
