# Preservation and projections

A record can contain deeply nested, heterogeneous metadata that does not fit a
single useful query schema. The library therefore stores two representations:
the serialized record and a selected set of typed Arrow columns.

## The document is authoritative

`__record_json` stores `OGCRecord.to_dict(transform_hrefs=False)`.
Readers reconstruct records from this payload through `OGCRecord.from_dict()`.
They do not reconstruct documents from query columns.

This separation permits a field to appear only in later records or have
different shapes across records without requiring it to be an Arrow column.
An explicit projection can select the fields your service needs.

Changing a query column does not edit the record. To change the document,
recover the `OGCRecord`, use its APIs, and serialize it again.

## Preservation starts at the PySTAC boundary

The package preserves the extension's serialized values, not raw source bytes.
PySTAC handles record construction, links, assets, and timestamp normalization.
For example, timestamps are normalized to UTC whole seconds, and absent links
may become an empty list.

The storage layer validates that the resulting document contains finite JSON
values and string keys. It rejects tuples and non-string keys instead of allowing
the JSON encoder to silently coerce them. Decoding rejects duplicate keys.
Validation checks existing containers without making a second deep copy.

Relative hrefs are serialized without transformation. Source self links, when
present, are included. An independent recovered record can be edited without
changing the file or another recovered record.

## Query geometry and document geometry have different roles

The binary geometry column supports spatial tools. Its bbox is derived from
geometry and provides a two-dimensional covering.
The original serialized geometry and bbox remain in the payload, including
foreign geometry members and a possible six-coordinate bbox.

Null and empty geometries have a null covering. An empty geometry still has a
WKB representation; a null geometry does not.

## Predictability has a storage cost

Each batch uses the same projection schema. Conversion consumes input once,
in order, and does not perform full-file schema inference or disk-backed schema
unification. This makes projection choices explicit.

The payload adds storage alongside the columns. Batching limits the number of
records processed together, but is not a fixed memory bound: document size and
Arrow allocations also matter. No throughput or compression benchmark is
promised by the API.

See [projection how-to](../how-to/project-filter.md) and
[storage reference](../reference/storage-format.md).
