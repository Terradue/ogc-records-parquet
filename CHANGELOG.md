# Changelog

Notable changes to this project are recorded here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

This history was reconstructed from version changes in
`src/ogc_records_parquet/__about__.py` and their associated code changes.
Dates are version-commit dates, not independently verified publication dates;
the repository has no release tags. The available history starts at `0.2.0`,
so earlier versions mentioned in documentation are not reconstructed here.

## Unreleased

### Added

- Dependencies on `pystac-ext-ogc-record` and the Terradue PySTAC fork with
  validation support.
- Migration guidance and integration tests for PySTAC metadata accessors,
  links, assets, file I/O, and relative href preservation.

### Changed

- **Breaking:** `records_to_arrow` accepts `OGCRecord` objects instead of
  dictionaries. `arrow_to_records` and `read_parquet` return `OGCRecord` objects.
  Existing dictionaries must be parsed with `OGCRecord.from_dict`.
- **Breaking:** Stored payloads follow `OGCRecord.to_dict()` serialization.
  Metadata timestamps and STAC temporal fields are normalized to UTC whole
  seconds, and some optional members are normalized. Exact raw-JSON identity,
  fractional timestamp precision, and every null-versus-absence distinction
  are no longer guaranteed. Legacy payloads also use the extension's parsing
  rules when read.
- Record parsing and serialization now use the PySTAC extension APIs.
  Stored links retain their relative hrefs, and self links are included.
- Updated the query notebook and regression tests to use `OGCRecord` objects
  and compare their serialized values.

### Removed

- **Breaking:** The `ogc_records_parquet.json` module and its public
  `read_json`, `read_ndjson`, and `write_ndjson` helpers. Use
  `OGCRecord.from_file` and `record.save_object` for individual JSON files;
  container selection and NDJSON framing belong to the calling application.
- The custom Record-envelope validator, replaced by `OGCRecord.from_dict`
  parsing. Full OGC schema validation remains the caller's responsibility.

## 0.2.0 - 2026-10-09

### Added

- Initial version present in Git, with batched conversion between OGC Record
  dictionaries and Arrow, plus atomic local GeoParquet writes and reads.
- Authoritative JSON payload storage alongside configurable typed query
  projections, including nested property paths and safe Arrow casts.
- CRS84 geometry storage as WKB with GeoArrow and GeoParquet metadata,
  derived bounding-box columns, and support for null and empty geometries.
- Explicit per-row collection membership through `collection_ids` and
  `read_collection_ids`, independent of Record identifiers and payloads.
- Catalog descriptions and versioned storage metadata, exposed through
  `read_collections` and `read_metadata`.
- Storage format `1.1.0` writing and compatibility with format `1.0.0` reads;
  legacy files return unknown collection membership.
- JSON readers for individual Records, arrays, FeatureCollections, and inline
  catalogs, together with streaming NDJSON input and atomic NDJSON output.
- Eleven example Records across two collections and a notebook demonstrating
  collection filtering and CQL2 queries with DuckDB.
- Typed package interfaces, regression tests, and Hatch quality checks for
  formatting, linting, typing, and security.
