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

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

import json

import pyarrow as pa
import pytest
from pystac import Link
from pystac.extensions.ogc_record import OGCRecord

from ogc_records_parquet import (
    arrow_to_records,
    read_parquet,
    records_to_arrow,
    to_parquet,
)


def test_explicit_schema_projects_later_fields_and_nested_lists(
    record: OGCRecord, tmp_path: Path
) -> None:
    fields: list[pa.Field[pa.DataType]] = [
        pa.field("id", pa.string(), nullable=False),
        pa.field("properties.extra", pa.int64()),
        pa.field("links", pa.list_(pa.struct([pa.field("href", pa.string())]))),
    ]
    schema = pa.schema(fields)
    later = OGCRecord(id="later", properties={"extra": 3, "unprojected": {"empty": {}}})
    later.add_link(Link("related", "https://example.org/a", extra_fields={"custom": [True]}))
    table = records_to_arrow([record, later], schema=schema, batch_size=1).read_all()
    assert table["properties.extra"].to_pylist() == [None, 3]
    assert table["links"].to_pylist() == [[], [{"href": "https://example.org/a"}]]
    path = tmp_path / "schema.parquet"
    to_parquet(table, path)
    assert [item.to_dict(transform_hrefs=False) for item in read_parquet(path)] == [
        record.to_dict(transform_hrefs=False),
        later.to_dict(transform_hrefs=False),
    ]


@pytest.mark.parametrize("value", [2.5, "wrong", 2**64])
def test_rejects_lossy_or_incompatible_integer_projection(record: OGCRecord, value: object) -> None:
    document = record.clone()
    document.properties["number"] = value
    schema = pa.schema([pa.field("properties.number", pa.int64())])
    with pytest.raises(ValueError, match="Cannot safely project"):
        records_to_arrow([document], schema=schema).read_all()


def test_missing_nonnullable_projection_is_rejected(record: OGCRecord) -> None:
    schema = pa.schema([pa.field("missing", pa.string(), nullable=False)])
    with pytest.raises(ValueError, match="Non-nullable"):
        records_to_arrow([record], schema=schema).read_all()


@pytest.mark.parametrize("name", ["geometry", "bbox", "__record_json", "", "properties..title"])
def test_reserved_or_ambiguous_projection_names_are_rejected(name: str) -> None:
    with pytest.raises(ValueError, match="projection name"):
        records_to_arrow([], schema=pa.schema([pa.field(name, pa.string())]))


def test_duplicate_projection_names_are_rejected() -> None:
    with pytest.raises(ValueError, match="unique"):
        records_to_arrow([], schema=pa.schema([pa.field("id", pa.string())] * 2))


def test_timestamp_projection_uses_extension_normalization(record: OGCRecord) -> None:
    schema = pa.schema([pa.field("properties.created", pa.timestamp("ns", tz="UTC"))])
    table = records_to_arrow([record], schema=schema).read_all()
    assert table["properties.created"].type == pa.timestamp("ns", tz="UTC")
    expected_epoch_nanoseconds = 1767269594000000000
    assert table["properties.created"].cast(pa.int64()).to_pylist() == [expected_epoch_nanoseconds]
    assert [item.to_dict(transform_hrefs=False) for item in arrow_to_records(table)] == [
        record.to_dict(transform_hrefs=False)
    ]


def test_empty_projection_schema_preserves_whole_document(record: OGCRecord) -> None:
    table = records_to_arrow([record], schema=pa.schema([])).read_all()
    assert [item.to_dict(transform_hrefs=False) for item in arrow_to_records(table)] == [
        record.to_dict(transform_hrefs=False)
    ]


@pytest.mark.parametrize("batch_size", [0, -1])
def test_invalid_batch_size_is_rejected(batch_size: int, tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="batch_size"):
        records_to_arrow([], batch_size=batch_size)
    with pytest.raises(ValueError, match="batch_size"):
        list(read_parquet(tmp_path / "missing.parquet", batch_size=batch_size))


def test_unknown_format_version_is_rejected(record: OGCRecord) -> None:
    table = records_to_arrow([record]).read_all()
    metadata = dict(table.schema.metadata)
    document = json.loads(metadata[b"ogc-records-parquet"])
    document["version"] = "999"
    metadata[b"ogc-records-parquet"] = json.dumps(document).encode()
    with pytest.raises(ValueError, match="Unsupported"):
        list(arrow_to_records(table.replace_schema_metadata(metadata)))


def test_metadata_and_payload_are_required(record: OGCRecord, tmp_path: Path) -> None:
    table = records_to_arrow([record]).read_all()
    with pytest.raises(ValueError, match=r"Missing.*metadata"):
        list(arrow_to_records(table.replace_schema_metadata(None)))
    with pytest.raises(ValueError, match=r"Missing.*payload"):
        list(arrow_to_records(table.drop(["__record_json"])))
    with pytest.raises(ValueError, match=r"Missing.*metadata"):
        to_parquet(pa.table({"id": ["a"]}), tmp_path / "invalid.parquet")


@pytest.mark.parametrize("column", ["geometry", "bbox", "__record_json"])
def test_parquet_rejects_incomplete_storage_columns(
    record: OGCRecord, column: str, tmp_path: Path
) -> None:
    table = records_to_arrow([record]).read_all().drop([column])
    with pytest.raises(ValueError, match="Missing required"):
        to_parquet(table, tmp_path / "invalid.parquet")
    assert not (tmp_path / "invalid.parquet").exists()


def test_parquet_rejects_changed_storage_type(record: OGCRecord, tmp_path: Path) -> None:
    table = records_to_arrow([record]).read_all()
    changed = table.set_column(
        table.schema.get_field_index("geometry"), "geometry", pa.array(["bad"])
    )
    with pytest.raises(ValueError, match="binary WKB"):
        to_parquet(changed, tmp_path / "invalid.parquet")


def test_reader_rejects_null_or_corrupt_payload(record: OGCRecord) -> None:
    table = records_to_arrow([record]).read_all()
    index = table.schema.get_field_index("__record_json")
    for payload in [None, "not-json", '{"id":"wrong"}', '{"id":1,"id":2}', '{"value":NaN}']:
        damaged = table.set_column(
            index, "__record_json", pa.array([payload], type=pa.large_string())
        )
        with pytest.raises(ValueError):
            list(arrow_to_records(damaged))


@pytest.mark.parametrize(
    ("custom", "message"),
    [
        ('{"nested":{"key":1,"key":2}}', "Duplicate JSON key"),
        ('{"nested":[NaN]}', "finite"),
        ('{"nested":[Infinity]}', "finite"),
        ('{"nested":[-Infinity]}', "finite"),
        ('{"nested":[1e400]}', "finite"),
    ],
)
def test_reader_rejects_invalid_nested_json(record: OGCRecord, custom: str, message: str) -> None:
    table = records_to_arrow([record]).read_all()
    payload = json.dumps(record.to_dict(transform_hrefs=False))
    payload = payload[:-1] + ', "custom":' + custom + "}"
    damaged = table.set_column(
        table.schema.get_field_index("__record_json"),
        "__record_json",
        pa.array([payload], type=pa.large_string()),
    )
    with pytest.raises(ValueError, match=message):
        list(arrow_to_records(damaged))


def test_rejects_malformed_catalog_metadata() -> None:
    with pytest.raises(ValueError, match="catalog JSON objects"):
        records_to_arrow([], collections={"wrong": "not a catalog"})
