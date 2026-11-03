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

"""Build safe query projections while preserving authoritative JSON payloads."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator, Sequence

    from pystac.extensions.ogc_record import OGCRecord

import itertools
import json

import pyarrow as pa
from shapely import to_wkb
from shapely.errors import ShapelyError
from shapely.geometry import shape

from ogc_records_parquet._json import JSONObject, JSONValue, require_json_object
from ogc_records_parquet._schema import value_at_path


def record_batches(
    records: Iterable[OGCRecord],
    projections: pa.Schema,
    schema: pa.Schema,
    batch_size: int,
    collection_ids: Iterable[str | None] | None = None,
) -> Iterator[pa.RecordBatch]:
    """Yield equally typed batches in source order from a one-pass iterable."""
    pairs = _pair_memberships(records, collection_ids)
    while chunk := tuple(itertools.islice(pairs, batch_size)):
        documents = [
            require_json_object(record.to_dict(transform_hrefs=False)) for record, _ in chunk
        ]
        memberships = [membership for _, membership in chunk]
        yield _make_batch(documents, projections, schema, memberships)


def _pair_memberships(
    records: Iterable[OGCRecord], collection_ids: Iterable[str | None] | None
) -> Iterator[tuple[OGCRecord, str | None]]:
    """Align explicit memberships with Records without truncating either stream.

    Raises:
        ValueError: If lengths differ or a membership is not a non-empty string or null.
    """
    if collection_ids is None:
        yield from ((record, None) for record in records)
        return
    for record, membership in zip(records, collection_ids, strict=True):
        if membership is not None and (not isinstance(membership, str) or membership == ""):
            raise ValueError("Collection membership must be a non-empty string or null")
        yield record, membership


def _make_batch(
    documents: Sequence[JSONObject],
    projections: pa.Schema,
    schema: pa.Schema,
    memberships: Sequence[str | None],
) -> pa.RecordBatch:
    arrays = [_project_field(documents, field) for field in projections]
    geometries = [_geometry_columns(document["geometry"]) for document in documents]
    arrays.extend(
        [
            pa.array([geometry for geometry, _ in geometries], type=pa.binary()),
            pa.array([bounds for _, bounds in geometries], type=schema.field("bbox").type),
            pa.array(memberships, type=pa.string()),
            pa.array(
                [
                    json.dumps(document, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
                    for document in documents
                ],
                type=pa.large_string(),
            ),
        ]
    )
    return pa.RecordBatch.from_arrays(arrays, schema=schema)


def _project_field(
    documents: Sequence[JSONObject], field: pa.Field[pa.DataType]
) -> pa.Array[pa.Scalar[pa.DataType]]:
    values = [value_at_path(document, field.name) for document in documents]
    if field.name == "id" and pa.types.is_string(field.type):
        values = [str(value) for value in values]
    try:
        # pyarrow-stubs requires mask; the public runtime API defaults it to None.
        inferred_type = pa.infer_type(values)  # type: ignore[call-arg]
        array = pa.array(values, type=inferred_type).cast(field.type, safe=True)
    except (
        pa.ArrowInvalid,
        pa.ArrowTypeError,
        pa.ArrowNotImplementedError,
        OverflowError,
    ) as error:
        raise ValueError(
            f"Cannot safely project {field.name!r} as {field.type}: {error}"
        ) from error
    if not field.nullable and array.null_count:
        raise ValueError(f"Non-nullable projection {field.name!r} contains missing or null values")
    return array


def _geometry_columns(geometry: JSONValue) -> tuple[bytes | None, JSONObject | None]:
    """Encode nullable CRS84 geometry and derive its two-dimensional covering."""
    if geometry is None:
        return None, None
    if not isinstance(geometry, dict):
        raise ValueError("Record geometry must be a GeoJSON object or null")
    try:
        parsed_geometry = shape(geometry)
        encoded: bytes = to_wkb(parsed_geometry, flavor="iso")
    except (ValueError, TypeError, KeyError, AttributeError, ShapelyError) as error:
        raise ValueError(f"Cannot encode GeoJSON geometry: {error}") from error
    if parsed_geometry.is_empty:
        return encoded, None
    bounds: JSONObject = dict(
        zip(("xmin", "ymin", "xmax", "ymax"), parsed_geometry.bounds, strict=True)
    )
    return encoded, bounds
