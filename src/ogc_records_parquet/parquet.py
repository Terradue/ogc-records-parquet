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

"""Write atomic GeoParquet files and read preserved documents or catalog metadata."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from collections.abc import Iterator

    from pystac.extensions.ogc_record import OGCRecord

    from ogc_records_parquet._json import JSONObject

import tempfile
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from ogc_records_parquet._schema import (
    MEMBERSHIP_COLUMN,
    read_format_metadata,
    validate_membership_schema,
    validate_storage_schema,
)
from ogc_records_parquet.arrow import arrow_to_records


def to_parquet(
    table: pa.Table | pa.RecordBatchReader,
    path: str | Path,
    *,
    compression: Literal["gzip", "brotli", "lz4", "zstd", "snappy", "none"] = "zstd",
) -> None:
    """Write a library-produced Arrow stream to a local GeoParquet file.

    Consumes batches in source order and replaces an existing destination only
    after successful conversion and writing. A failed conversion leaves the
    destination unchanged. Temporary data is created in the destination directory.
    Remote/object-storage paths are not supported.

    Schema metadata and the supplied storage format version are retained;
    writing a valid legacy stream does not upgrade it. Storage structure is
    checked, but arbitrary input tables do not receive per-payload Record or
    OGC schema validation.

    Args:
        table: A table or unconsumed reader produced by `records_to_arrow()`,
            or an equivalent table retaining the required storage columns and
            metadata. A reader is consumed from its current position; a table
            can be reused. Empty input still creates a file with its schema.
        path: Local destination file. Its parent directory must already exist.
            An existing file is replaced on success.
        compression: Parquet codec, defaulting to `"zstd"`. Use `"none"` for
            uncompressed output. Codec availability depends on the PyArrow build.

    Raises:
        ValueError: If format metadata or required storage columns are invalid,
            or if lazy record conversion raises a validation error.
        OSError: If the destination directory is absent, inaccessible, or a file
            operation fails.

    Examples:
        Write a local file and read its records:

        >>> from pathlib import Path
        >>> from tempfile import TemporaryDirectory
        >>> from pystac.extensions.ogc_record import OGCRecord
        >>> from ogc_records_parquet import read_parquet, records_to_arrow, to_parquet
        >>> with TemporaryDirectory() as directory:
        ...     path = Path(directory) / "records.parquet"
        ...     to_parquet(records_to_arrow([OGCRecord(id="workflow")]), path)
        ...     identifiers = [record.id for record in read_parquet(path)]
        >>> identifiers
        ['workflow']
    """
    validate_storage_schema(table.schema)
    destination = Path(path)
    with tempfile.TemporaryDirectory(
        prefix=".records-parquet-", dir=destination.parent
    ) as directory:
        staging = Path(directory) / "records.parquet"
        batches = table.to_batches() if isinstance(table, pa.Table) else table
        with pq.ParquetWriter(staging, table.schema, compression=compression) as writer:
            for batch in batches:
                writer.write_batch(batch)
        staging.replace(destination)


def read_parquet(path: str | Path, *, batch_size: int = 1024) -> Iterator[OGCRecord]:
    """Read OGCRecord objects in file order from GeoParquet.

    Opens the file and validates its format when iteration begins. Records are
    reconstructed from their stored JSON payloads, not from query projections.
    Storage formats `1.0.0` and `1.1.0` are accepted; current PySTAC parsing
    and normalization apply to both.

    The file remains open while the iterator is active. Exhaust the iterator or
    call its `close()` method when abandoning iteration early.

    Args:
        path: Parquet file produced by this library, retaining format metadata,
            payloads, and the membership schema required by its format version.
        batch_size: Maximum rows per decoded batch, greater than zero. It does
            not limit the total number of yielded records or their size.

    Yields:
        Independent OGCRecord objects in file order. Empty files yield no records.
        Storage-only memberships are available separately through
        `read_collection_ids()`; they are not injected into the records.

    Raises:
        ValueError: During iteration if the batch size is invalid, format metadata
            or membership schema is missing or incompatible, or a stored payload
            fails JSON or Record validation.
        TypeError: If PySTAC cannot parse a metadata timestamp's Python type.
        OSError: If the file cannot be opened or read.
    """
    if batch_size < 1:
        raise ValueError("batch_size must be greater than zero")
    with pq.ParquetFile(path) as parquet_file:
        schema = parquet_file.schema_arrow
        validate_membership_schema(schema)
        reader = pa.RecordBatchReader.from_batches(
            schema, parquet_file.iter_batches(batch_size=batch_size)
        )
        yield from arrow_to_records(reader)


def read_metadata(path: str | Path) -> JSONObject:
    """Read the library's format metadata without decoding Record payloads.

    Reads the Parquet schema and returns its `ogc-records-parquet` metadata.
    It does not return the complete Arrow or GeoParquet metadata, validate
    storage column types, or inspect row membership values.

    Args:
        path: Parquet file containing supported library format metadata.

    Returns:
        A newly decoded object containing `version`, `payload_column`, and,
        for format `1.1.0`, `membership_column`. Library-created metadata also
        includes `writer_version`, `projections`, and optional `collections`.
        Modifying this object does not change the file.

    Raises:
        ValueError: If metadata is missing, malformed JSON, uses an unsupported
            version, or declares unsupported payload or membership column names.
        OSError: If the file cannot be opened or its schema cannot be read.
    """
    return read_format_metadata(pq.read_schema(path))


def read_collections(path: str | Path) -> JSONObject:
    """Read stored collection descriptions independently of row membership.

    Only schema metadata is read; Record payloads are not decoded. Descriptions
    neither assign membership nor validate the IDs in `__collection_id`.

    Args:
        path: Parquet file containing supported library format metadata.

    Returns:
        A newly decoded mapping of catalog descriptions keyed by collection ID.
        Returns an empty mapping when descriptions are absent or explicitly
        empty. Catalog contents and the relationship between mapping keys and
        catalog IDs are not semantically validated. Changes do not alter the file.

    Raises:
        ValueError: If format metadata is missing or invalid, or the stored
            `collections` value is not a JSON object.
        OSError: If the file cannot be opened or its schema cannot be read.
    """
    collections = read_metadata(path).get("collections", {})
    if not isinstance(collections, dict):
        raise ValueError("Stored collections metadata must be an object")
    return collections


def read_collection_ids(path: str | Path, *, batch_size: int = 1024) -> Iterator[str | None]:
    """Read storage-only memberships in file row order, independently of Record JSON.

    File access and validation begin on iteration. Format `1.1.0` reads only
    the membership column; Record payloads are not decoded or validated. Format
    `1.0.0` returns unknown membership for every row, even if descriptions or
    a similarly named column exist.

    The file remains open until the iterator is exhausted or closed. Pair its
    results with records only when reading identical rows in identical order.
    Duplicate record IDs do not affect membership.

    Args:
        path: A library-produced Parquet file in format 1.0.0 or 1.1.0.
        batch_size: Maximum membership rows read per batch, greater than zero.
            It does not limit the total number of yielded memberships.

    Yields:
        One non-empty collection ID or `None` per row. IDs need not have a
        corresponding stored description. Empty files yield no values.

    Raises:
        ValueError: During iteration if batch size or format metadata is invalid,
            format `1.1.0` lacks a single nullable string membership column, or
            a stored membership is neither a non-empty string nor null.
        OSError: If the file cannot be opened or read.
    """
    if batch_size < 1:
        raise ValueError("batch_size must be greater than zero")
    with pq.ParquetFile(path) as parquet_file:
        validate_membership_schema(parquet_file.schema_arrow)
        metadata = read_format_metadata(parquet_file.schema_arrow)
        if metadata["version"] == "1.0.0":
            yield from (None for _ in range(parquet_file.metadata.num_rows))
            return
        for batch in parquet_file.iter_batches(batch_size=batch_size, columns=[MEMBERSHIP_COLUMN]):
            for value in batch.column(MEMBERSHIP_COLUMN):
                membership = value.as_py()
                if membership is not None and (not isinstance(membership, str) or membership == ""):
                    raise ValueError("Collection membership must be a non-empty string or null")
                yield membership
