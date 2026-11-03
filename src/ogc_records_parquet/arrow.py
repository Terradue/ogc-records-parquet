# Copyright 2026 Terradue
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Convert Record documents to Arrow streams and back using PySTAC OGCRecord objects."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator, Mapping


import pyarrow as pa
from pystac.extensions.ogc_record import OGCRecord

from ogc_records_parquet._conversion import record_batches
from ogc_records_parquet._json import loads_object, require_json_object
from ogc_records_parquet._schema import (
    PAYLOAD_COLUMN,
    default_schema,
    read_format_metadata,
    storage_schema,
    validate_schema,
)


def records_to_arrow(
    records: Iterable[OGCRecord],
    *,
    schema: pa.Schema | None = None,
    batch_size: int = 1024,
    collections: Mapping[str, object] | None = None,
    collection_ids: Iterable[str | None] | None = None,
) -> pa.RecordBatchReader:
    """Project Records into a lazy Arrow stream with PySTAC-serialized payloads.

    Record and membership iterables are consumed only when the reader is
    advanced. Records are serialized at that time, so changes made before
    consumption are visible. Collection descriptions are instead validated and
    serialized immediately. The input records and descriptions are not modified.

    Each row retains the document produced by
    `OGCRecord.to_dict(transform_hrefs=False)`, including self links and
    unmodified relative hrefs. PySTAC normalization applies before storage;
    original JSON bytes and pre-normalization timestamp precision are not
    preserved. Null geometry and records without STAC temporal fields are
    supported. Non-null geometry must already use CRS84 longitude/latitude.

    Args:
        records: One-pass iterable of OGCRecord objects in source order. Serialization
            and conversion happen during consumption; duplicate IDs are allowed.
        schema: Query projection fields. Dot-separated names select nested object
            keys; this is not an OGC API validation schema. `None` selects
            `default_schema()`; an empty schema selects no query fields. Missing
            paths project as null, which is rejected for non-nullable fields.
            Paths cannot traverse lists or escape dots in keys. Reserved columns
            `geometry`, `bbox`, `__record_json`, and `__collection_id` are always
            added and cannot be named as projections. Unprojected members remain
            in the payload. Custom schema metadata is retained except for the
            library-owned `geo` and `ogc-records-parquet` keys.
        batch_size: Maximum number of records converted per batch, greater than zero.
            This is a row count, not a bound on memory use.
        collections: Catalog JSON objects indexed by string collection IDs. Stored
            as a metadata snapshot before this function returns. `None` omits
            descriptions; an empty mapping stores an empty descriptions object.
            Catalog schemas, description IDs, and membership references are not
            semantically validated.
        collection_ids: One-pass memberships aligned with Records, including nulls
            for unknown membership. Omission stores null for every row. Values must
            be non-empty strings or null, and the iterable must have exactly as many
            values as records. Membership is independent of original JSON fields
            and is not inferred from the supplied descriptions.

    Returns:
        A single-pass reader with a fixed schema, even for empty input. Call
        `read_all()` to materialize a reusable table, or pass the reader directly
        to `to_parquet()`. New streams use storage format `1.1.0`.

    Raises:
        ValueError: Immediately if the batch size, projection names, or collection
            JSON is invalid. During consumption if a record contains non-JSON or
            non-finite values, geometry cannot be encoded, a projection requires
            an unsafe cast or violates nullability, or memberships are invalid
            or differ in length. PySTAC may also reject malformed timestamps.
        TypeError: During consumption if PySTAC cannot serialize a metadata
            timestamp of the supplied Python type.

    Examples:
        Create a stream and inspect a default query column:

        >>> from pystac.extensions.ogc_record import OGCRecord
        >>> from ogc_records_parquet import records_to_arrow
        >>> record = OGCRecord(id="workflow", properties={"title": "Flood mapping"})
        >>> table = records_to_arrow([record], batch_size=1).read_all()
        >>> table["properties.title"].to_pylist()
        ['Flood mapping']
    """
    if batch_size < 1:
        raise ValueError("batch_size must be greater than zero")
    projections = default_schema() if schema is None else schema
    validate_schema(projections)
    catalogs = None if collections is None else require_json_object(dict(collections))
    if catalogs is not None and any(not isinstance(catalog, dict) for catalog in catalogs.values()):
        raise ValueError("Collection metadata must map IDs to catalog JSON objects")
    output_schema = storage_schema(projections, catalogs)
    batches = record_batches(records, projections, output_schema, batch_size, collection_ids)
    return pa.RecordBatchReader.from_batches(output_schema, batches)


def arrow_to_records(table: pa.Table | pa.RecordBatchReader) -> Iterator[OGCRecord]:
    """Decode OGCRecord objects from a library-produced Arrow stream.

    Stored payloads are authoritative: editing query or membership columns does
    not edit the exported records. Decoding follows `OGCRecord.from_dict()`,
    including its normalization rules for legacy payloads. No OGC profile
    validation is performed.

    Validation and decoding begin on iteration, not when this function is called.
    A supplied reader is consumed from its current position. A table is not
    modified. Storage formats `1.0.0` and `1.1.0` are accepted.

    Args:
        table: Table or stream retaining valid `ogc-records-parquet` schema
            metadata and `__record_json`. Payload columns may have Arrow string
            or large-string type, but every row must contain non-null JSON text.
            Geometry, membership, and query columns may be omitted.

    Yields:
        Independently decoded OGCRecord objects in row order. Changes to a yielded
        record do not modify the input or other yielded records. Empty input
        with valid metadata and payload schema yields no records.

    Raises:
        ValueError: During iteration if format metadata or payload columns are
            missing or incompatible, a payload is null or is not a JSON object,
            JSON contains duplicate keys or non-finite numbers, or PySTAC rejects
            the Record document. JSON syntax errors are `json.JSONDecodeError`,
            a subclass of `ValueError`.
        TypeError: If PySTAC cannot parse a metadata timestamp's Python type.

    Examples:
        Reconstruct from only the payload column, retaining schema metadata:

        >>> from pystac.extensions.ogc_record import OGCRecord
        >>> from ogc_records_parquet import arrow_to_records, records_to_arrow
        >>> table = records_to_arrow([OGCRecord(id="workflow")]).read_all()
        >>> restored = next(arrow_to_records(table.select(["__record_json"])))
        >>> restored.id
        'workflow'
    """
    read_format_metadata(table.schema)
    if PAYLOAD_COLUMN not in table.schema.names:
        raise ValueError("Missing original Record JSON payload column")
    payload_type = table.schema.field(PAYLOAD_COLUMN).type
    if not (pa.types.is_string(payload_type) or pa.types.is_large_string(payload_type)):
        raise ValueError("Original Record JSON payload column must contain strings")
    batches = table.to_batches() if isinstance(table, pa.Table) else table
    for batch in batches:
        for payload in batch.column(PAYLOAD_COLUMN):
            encoded = payload.as_py()
            if not isinstance(encoded, str):
                raise ValueError("Original Record JSON payload must be non-null")
            yield OGCRecord.from_dict(loads_object(encoded))
