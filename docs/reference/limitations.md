# Errors and limitations

## Failure timing

`records_to_arrow()` validates the projection schema, batch size, and collection
metadata immediately. Record conversion is lazy. Consume the reader or write it
to detect per-record failures. Generator readers likewise report errors when
iterated.

| Failure | Action |
| --- | --- |
| Invalid or reserved projection name | Use a unique non-empty object path; do not name a reserved storage column. |
| Unsafe projection conversion | Select a compatible Arrow type or leave the field unprojected. |
| Missing non-nullable projection | Supply the field or make the projection nullable. |
| Non-JSON or non-finite value | Replace tuples, unsupported Python objects, non-string keys, and NaN/infinity before storage. |
| Duplicate key in stored JSON | Correct the source payload; decoding rejects ambiguity. |
| Membership length mismatch | Align `collection_ids` with records before consumption. |
| Invalid membership | Use a non-empty string or `None`. |
| Missing format metadata or payload | Retain library metadata and `__record_json` when filtering/exporting Arrow results. |
| Unsupported format version | Use a reader supporting that format; changing the version label alone is not migration. |
| Missing destination directory | Create the parent directory before calling `to_parquet()`. |

Storage validation failures generally raise `ValueError`; JSON syntax errors
are `json.JSONDecodeError`, a `ValueError` subclass. Filesystem, PyArrow
writer, and PySTAC serialization errors can propagate. Error message text is
not a versioned interface.

## Limits

- OGC conformance, application profiles, and geometry topology are not validated.
- The package does not execute queries or translate CQL2.
- CRS84 inputs are required; reprojection and other input CRSs are not supported.
- Writes target local files, not remote or object-storage destinations.
- Batch size counts records; it is not a memory-size guarantee.
- JSON payload storage duplicates some values held in query columns.
- Projection schemas are explicit or use the defaults; there is no automatic
  full-file inference, first-batch inference, or disk-backed schema unification.
- Raw source JSON bytes and timestamp precision before PySTAC normalization
  are not preserved.

## Failed writes

Local writes stage data in the destination directory and replace the target
after success. A conversion failure leaves an existing destination unchanged.
This behavior is not a transaction spanning multiple files or a remote storage
guarantee.
