# Migrate existing applications and files

## Replace the dictionary API

The current API accepts `OGCRecord` instances. Replace direct dictionary
inputs with `OGCRecord.from_dict(document)`. Returned values are also
`OGCRecord` instances; use `to_dict()` at JSON boundaries.

The old `ogc_records_parquet.json` module and its `read_json`,
`read_ndjson`, and `write_ndjson` helpers have been removed.
Use [PySTAC file APIs](import-export.md) for individual documents and handle
container selection or NDJSON framing in your application.

## Check normalization expectations

Compare records against `OGCRecord.to_dict(transform_hrefs=False)`.
The extension normalizes metadata timestamps and STAC temporal fields to UTC
whole seconds, including nested metadata timestamps, and normalizes some
optional fields. Byte identity, fractional timestamp precision, and every
missing-versus-null distinction are not preserved.

These parsing rules also apply when reading legacy stored payloads.

## Rewrite a legacy file

Readers accept storage formats `1.0.0` and `1.1.0`. Legacy membership reads
as `None` for every row. To rewrite a legacy file with the current format,
run the following in a directory containing `legacy.parquet`:

```python
from ogc_records_parquet import (
    read_collection_ids,
    read_collections,
    read_parquet,
    records_to_arrow,
    to_parquet,
)

records = list(read_parquet("legacy.parquet"))
catalogs = read_collections("legacy.parquet")
to_parquet(
    records_to_arrow(records, collections=catalogs),
    "migrated.parquet",
)
assert list(read_collection_ids("migrated.parquet")) == [None] * len(records)
assert [record.to_dict() for record in read_parquet("migrated.parquet")] == [
    record.to_dict() for record in records
]
```

If a trustworthy external source provides memberships, pass its aligned
iterable as `collection_ids=` to `records_to_arrow()`. Do not infer membership
from titles, duplicate record IDs, or catalog descriptions alone.

Reserializing uses the default query projections unless you explicitly supply
a schema. Preserve any application-specific projections by passing that schema.
Merely copying an existing Arrow stream through `to_parquet()` preserves its
format version; it does not upgrade the stream.

See [format compatibility](../reference/storage-format.md#versions) for version
details.
