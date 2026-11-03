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

"""Define storage columns and projection paths independently of API schemas."""

from __future__ import annotations

import json

import pyarrow as pa
from pyproj import CRS

from ogc_records_parquet.__about__ import __version__
from ogc_records_parquet._json import JSONObject, JSONValue, loads_object

PAYLOAD_COLUMN = "__record_json"
METADATA_KEY = b"ogc-records-parquet"
FORMAT_VERSION = "1.1.0"
MEMBERSHIP_COLUMN = "__collection_id"
SUPPORTED_FORMAT_VERSIONS = frozenset({"1.0.0", FORMAT_VERSION})
RESERVED_COLUMNS = frozenset({PAYLOAD_COLUMN, MEMBERSHIP_COLUMN, "geometry", "bbox"})


def default_schema() -> pa.Schema:
    """Return stable query projections of common Records members.

    All fields are nullable. The projection names are literal Arrow column names
    and dot-separated lookup paths in serialized Record objects.

    | Field | Arrow type |
    | --- | --- |
    | `id` | string |
    | `type` | string |
    | `properties.type` | string |
    | `properties.title` | string |
    | `properties.description` | string |
    | `properties.created` | string |
    | `properties.updated` | string |
    | `properties.keywords` | list of string |

    Integer identifiers are converted to strings only in the query column.
    Timestamp columns contain PySTAC's serialized strings, including its
    normalization. Original serialized values remain authoritative in the
    payload. This schema does not validate OGC conformance.

    Returns:
        A new query schema without storage columns or format metadata.
        `records_to_arrow()` adds those when creating a stream. Pass a different
        schema to that function to select other fields or Arrow types.

    Examples:
        >>> from ogc_records_parquet import default_schema
        >>> schema = default_schema()
        >>> schema.field("properties.title").nullable
        True
        >>> "__record_json" in schema.names
        False
    """
    return pa.schema(
        [
            pa.field("id", pa.string()),
            pa.field("type", pa.string()),
            pa.field("properties.type", pa.string()),
            pa.field("properties.title", pa.string()),
            pa.field("properties.description", pa.string()),
            pa.field("properties.created", pa.string()),
            pa.field("properties.updated", pa.string()),
            pa.field("properties.keywords", pa.list_(pa.string())),
        ]
    )


def validate_schema(schema: pa.Schema) -> None:
    """Reject ambiguous or reserved projection names.

    Raises:
        ValueError: If fields are duplicated, reserved, empty, or contain empty paths.
    """
    names = schema.names
    if len(set(names)) != len(names):
        raise ValueError("Projection column names must be unique")
    for name in names:
        if name in RESERVED_COLUMNS or not all(name.split(".")):
            raise ValueError(f"Invalid or reserved projection name: {name!r}")


def value_at_path(document: JSONObject, path: str) -> JSONValue:
    """Resolve dot-separated object keys; missing values project as null."""
    value: JSONValue = document
    for segment in path.split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(segment)
    return value


def storage_schema(projections: pa.Schema, collections: JSONObject | None) -> pa.Schema:
    """Attach serialization columns and versioned metadata to query projections."""
    crs = CRS.from_user_input("OGC:CRS84").to_json_dict()
    geometry_metadata = {
        b"ARROW:extension:name": b"geoarrow.wkb",
        b"ARROW:extension:metadata": json.dumps({"crs": crs}).encode(),
    }
    bbox = pa.struct([pa.field(name, pa.float64()) for name in ("xmin", "ymin", "xmax", "ymax")])
    fields = [
        *projections,
        pa.field("geometry", pa.binary(), metadata=geometry_metadata),
        pa.field("bbox", bbox),
        pa.field(MEMBERSHIP_COLUMN, pa.string()),
        pa.field(PAYLOAD_COLUMN, pa.large_string(), nullable=False),
    ]
    metadata: dict[bytes | str, bytes | str] = dict((projections.metadata or {}).items())
    metadata[METADATA_KEY] = json.dumps(
        _format_metadata(projections, collections),
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    ).encode()
    metadata[b"geo"] = json.dumps(_geo_metadata(crs)).encode()
    return pa.schema(fields, metadata=metadata)


def _format_metadata(projections: pa.Schema, collections: JSONObject | None) -> JSONObject:
    metadata: JSONObject = {
        "version": FORMAT_VERSION,
        "writer_version": __version__,
        "payload_column": PAYLOAD_COLUMN,
        "membership_column": MEMBERSHIP_COLUMN,
        "projections": {name: list[JSONValue](name.split(".")) for name in projections.names},
    }
    if collections is not None:
        metadata["collections"] = collections
    return metadata


def _geo_metadata(crs: object) -> dict[str, object]:
    return {
        "version": "1.1.0",
        "primary_column": "geometry",
        "columns": {
            "geometry": {
                "encoding": "WKB",
                "geometry_types": [],
                "crs": crs,
                "edges": "planar",
                "covering": {
                    "bbox": {name: ["bbox", name] for name in ("xmin", "ymin", "xmax", "ymax")}
                },
            }
        },
    }


def read_format_metadata(schema: pa.Schema) -> JSONObject:
    """Read and check the serialization format version.

    Raises:
        ValueError: If metadata is missing or uses an unsupported version.
    """
    metadata = schema.metadata or {}
    if METADATA_KEY not in metadata:
        raise ValueError("Missing ogc-records-parquet metadata")
    document = loads_object(metadata[METADATA_KEY])
    version = document.get("version")
    if not isinstance(version, str) or version not in SUPPORTED_FORMAT_VERSIONS:
        raise ValueError("Unsupported ogc-records-parquet format version")
    if document.get("payload_column") != PAYLOAD_COLUMN:
        raise ValueError("Unsupported record payload column")
    if version == FORMAT_VERSION and document.get("membership_column") != MEMBERSHIP_COLUMN:
        raise ValueError("Unsupported membership column declaration")
    return document


def validate_membership_schema(schema: pa.Schema) -> None:
    """Check membership storage for full file schemas, allowing legacy absence.

    Raises:
        ValueError: If new-format membership storage is missing or incompatible.
    """
    metadata = read_format_metadata(schema)
    if metadata["version"] == "1.0.0":
        return
    if schema.names.count(MEMBERSHIP_COLUMN) != 1:
        raise ValueError("Missing or duplicate collection membership column")
    field = schema.field(MEMBERSHIP_COLUMN)
    if field.type != pa.string() or not field.nullable:
        raise ValueError("Collection membership column must be nullable string")


def validate_storage_schema(schema: pa.Schema) -> None:
    """Reject incomplete or incompatible serialization columns before writing.

    Raises:
        ValueError: If required columns or their storage types are incompatible.
    """
    validate_membership_schema(schema)
    if len(set(schema.names)) != len(schema.names):
        raise ValueError("Storage column names must be unique")
    required_columns = RESERVED_COLUMNS - {MEMBERSHIP_COLUMN}
    if not required_columns.issubset(schema.names):
        raise ValueError("Missing required geometry, bbox or payload storage columns")
    geometry = schema.field("geometry")
    if not pa.types.is_binary(geometry.type):
        raise ValueError("Storage geometry column must contain binary WKB")
    if (geometry.metadata or {}).get(b"ARROW:extension:name") != b"geoarrow.wkb":
        raise ValueError("Storage geometry column requires geoarrow.wkb metadata")
    expected_bbox = pa.struct(
        [pa.field(name, pa.float64()) for name in ("xmin", "ymin", "xmax", "ymax")]
    )
    if schema.field("bbox").type != expected_bbox:
        raise ValueError("Storage bbox column must have the four float64 covering fields")
    if schema.field(PAYLOAD_COLUMN).type != pa.large_string():
        raise ValueError("Storage payload column must contain large strings")
