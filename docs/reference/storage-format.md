# Storage format

## Versions

| Version domain | Current behavior |
| --- | --- |
| Package | Defined by `ogc_records_parquet.__version__`; independent of file versions |
| OGC Records storage format | `records_to_arrow()` creates `1.1.0`; readers accept `1.0.0` and `1.1.0` |
| GeoParquet metadata | `1.1.0` |

Format `1.1.0` declares and stores row membership. Format `1.0.0` has no
membership contract; its membership reader returns null for each row.
Package `0.1.0` readers reject format `1.1.0` files.

`to_parquet()` preserves a supplied valid legacy schema and version.
To create the current format from older records, use
[the migration procedure](../how-to/migrate.md).

## Reserved columns

| Name | Arrow type | Meaning |
| --- | --- | --- |
| `geometry` | binary, nullable | ISO WKB, in CRS84 longitude/latitude coordinates |
| `bbox` | nullable struct of four float64 fields | Geometry-derived two-dimensional covering |
| `__collection_id` | string, nullable | Storage-only membership; non-empty string or null |
| `__record_json` | large_string, non-nullable | Authoritative serialized Record document |

The bbox field order is `xmin`, `ymin`, `xmax`, `ymax`.
Null and empty geometry have null covering values. An original JSON bbox is
retained independently in the payload.

The geometry field metadata contains:

- `ARROW:extension:name = geoarrow.wkb`.
- `ARROW:extension:metadata`, with a JSON-encoded CRS84 definition.

There is no reprojection. Inputs must already use CRS84.

## Query projections

`default_schema()` returns the following nullable query fields, before storage
columns and format metadata are added:

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

Projection field names select dot-separated paths through objects. Missing
paths or paths passing through a non-object produce null. Lists are projected
as a whole; list traversal and escaping literal dots in keys are not supported.

Names must be unique, non-empty, and have no empty path segments. Reserved
column names cannot be supplied as projections.

The default `id` projection is string-valued, including for integer identifiers.
The integer remains an integer in the payload. Default timestamp projections
are strings containing the extension's normalized values.

Other projection values use inferred Arrow types followed by safe casts to the
requested field types. Missing/null values in a non-nullable field fail.
Unprojected fields remain in the payload.

## Schema metadata

Existing projection schema metadata is retained except for the library-owned
`geo` and `ogc-records-parquet` keys, which are replaced.

### geo

The GeoParquet declaration specifies:

- Version `1.1.0` and primary column `geometry`.
- WKB encoding, planar edges, and CRS84.
- An empty `geometry_types` list.
- Covering paths pointing to the four `bbox` struct fields.

### ogc-records-parquet

The JSON object has these fields:

| Field | Meaning |
| --- | --- |
| `version` | Storage format version |
| `writer_version` | Package version that created the schema |
| `payload_column` | `__record_json` |
| `membership_column` | `__collection_id` in format `1.1.0` |
| `projections` | Mapping from projected names to lists of path segments |
| `collections` | Optional mapping of IDs to catalog JSON objects |

Catalog descriptions do not assign row membership. Unknown membership remains
null even if only one catalog description exists.

## Payload contract

The payload is JSON text from `OGCRecord.to_dict(transform_hrefs=False)`.
It preserves the extension's serialized values, includes self links when
present, and leaves relative hrefs unchanged.

Readers use `OGCRecord.from_dict()`. Query columns are not used to reconstruct
the payload. Whitespace, escape spelling, member order, and pre-PySTAC
normalization details are outside the preservation contract.
