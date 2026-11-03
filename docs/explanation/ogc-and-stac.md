# OGC Records and STAC

`OGCRecord` is supplied by
[pystac-ext-ogc-record](https://terradue.github.io/pystac-ext-ogc-record/).
It provides PySTAC-compatible links, assets, and metadata APIs while retaining
OGC Record serialization.

## Object compatibility does not imply document equivalence

An OGC Record may describe a service without geometry or a STAC temporal extent.
OGC `time` and STAC datetime fields are separate concepts. Storing an OGC
Record must not invent an observation time or move OGC fields to fit a STAC
document.

The extension's explicit `to_stac_item()` conversion requires a STAC temporal
extent. This library does not call that method during storage.

## Relationship to stac-geoparquet

[stac-geoparquet](https://github.com/stac-utils/stac-geoparquet) provides
STAC-oriented conversion and shares the underlying Arrow, WKB, and GeoParquet
building blocks. It is credited in the repository's `NOTICE`.

This library's contract additionally keeps the full OGC payload and
storage-only membership separate from the query columns. These are local
format choices; an OGC Records Parquet file is not automatically a
STAC-GeoParquet document.

The implementation depends directly on PySTAC, PyArrow, Shapely, and PyProj.
It does not import or patch `stac-geoparquet` internals.

## Membership is an external association

A catalog description explains a collection. It does not identify which rows
belong to it. The nullable `__collection_id` column stores that association
explicitly, independently of record IDs and of any `collection` member in
the original document.

This permits duplicate IDs across collections and unknown membership.
It also means an old file containing only descriptions cannot reveal lost
memberships without an external source.

## Validation responsibilities

The package checks storage types, JSON representability, projection safety,
and format compatibility. OGC conformance and profile validation belong to
the caller. `OGCRecord.validate()` needs an explicitly supplied OGC validator;
the storage pipeline does not perform that validation automatically.

See [collection membership](../how-to/collections.md) for practical usage.
