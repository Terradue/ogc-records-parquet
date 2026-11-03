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
    from collections.abc import Iterator
    from pathlib import Path

import json

import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from pystac.extensions.ogc_record import OGCRecord

from ogc_records_parquet import (
    JSONObject,
    __version__,
    arrow_to_records,
    read_collections,
    read_metadata,
    read_parquet,
    records_to_arrow,
    to_parquet,
)


def _canonical(records: list[OGCRecord]) -> str:
    return json.dumps(
        [record.to_dict(transform_hrefs=False) for record in records],
        sort_keys=True,
        ensure_ascii=False,
        allow_nan=False,
    )


@pytest.mark.parametrize("batch_size", [1, 3, 1024])
def test_all_supplied_examples_roundtrip(
    example_records: list[OGCRecord], batch_size: int, tmp_path: Path
) -> None:
    assert example_records
    table = records_to_arrow(example_records, batch_size=batch_size).read_all()
    assert _canonical(list(arrow_to_records(table))) == _canonical(example_records)
    path = tmp_path / "examples.parquet"
    to_parquet(table, path)
    assert _canonical(list(read_parquet(path, batch_size=2))) == _canonical(example_records)
    assert table["geometry"].null_count == len(example_records)


def test_preserves_collisions_extensions_and_heterogeneous_values(
    tmp_path: Path,
) -> None:
    record = OGCRecord(
        id=12,
        time={"interval": ["2020-01-01", ".."]},
        conforms_to=["https://example.org/profile"],
        link_templates=[{"uriTemplate": "https://example.org/{id}"}],
        extra_fields={"extension": {"empty": {}, "values": [1, "x", None, {"a": True}]}},
        properties={"type": "service", "id": "property-id", "geometry": "property-value"},
    )
    other = OGCRecord(
        id="next",
        properties={"type": "dataset", "extension": None},
        extra_fields={"extension": []},
    )
    original = [record, other]
    table = records_to_arrow(original, batch_size=1).read_all()
    assert table["id"].to_pylist() == ["12", "next"]
    assert table["type"].to_pylist() == ["Feature", "Feature"]
    assert table["properties.type"].to_pylist() == ["service", "dataset"]
    path = tmp_path / "extensions.parquet"
    to_parquet(table, path)
    assert _canonical(list(read_parquet(path))) == _canonical(original)


@pytest.mark.parametrize("properties", [{}, None])
def test_empty_or_null_properties(
    record: OGCRecord, properties: dict[str, object] | None, tmp_path: Path
) -> None:
    changed = OGCRecord(id=record.id, properties=properties)
    table = records_to_arrow([changed]).read_all()
    path = tmp_path / "empty.parquet"
    to_parquet(table, path)
    assert [item.to_dict(transform_hrefs=False) for item in read_parquet(path)] == [
        changed.to_dict(transform_hrefs=False)
    ]


def test_empty_input_has_schema_and_writable_file(tmp_path: Path) -> None:
    reader = records_to_arrow([])
    path = tmp_path / "empty.parquet"
    to_parquet(reader, path)
    assert list(read_parquet(path)) == []
    assert read_collections(path) == {}


def test_collections_versions_and_custom_metadata(record: OGCRecord, tmp_path: Path) -> None:
    catalogs: JSONObject = {
        "applications": {"id": "applications", "type": "Collection", "links": []},
        "data": {"id": "data", "type": "Collection", "links": [], "extension": {}},
    }
    schema = pa.schema([pa.field("id", pa.string())], metadata={b"custom": b"retained"})
    path = tmp_path / "metadata.parquet"
    to_parquet(records_to_arrow([record], schema=schema, collections=catalogs), path)
    assert read_collections(path) == catalogs
    metadata = read_metadata(path)
    assert metadata["version"] == "1.1.0"
    assert metadata["writer_version"] == __version__
    assert pq.read_schema(path).metadata[b"custom"] == b"retained"
    empty_path = tmp_path / "empty-catalogs.parquet"
    to_parquet(records_to_arrow([], collections={}), empty_path)
    assert read_metadata(empty_path)["collections"] == {}


def test_collection_metadata_is_snapshotted_before_consumption(tmp_path: Path) -> None:
    keywords = ["original"]
    catalog = {"keywords": keywords}
    collections = {"applications": catalog}
    reader = records_to_arrow([], collections=collections)

    keywords.append("later")
    catalog["keywords"] = ["replacement"]
    collections.clear()

    path = tmp_path / "snapshot.parquet"
    to_parquet(reader, path)
    assert read_collections(path) == {"applications": {"keywords": ["original"]}}


def test_single_pass_lazy_consumption_and_order(record: OGCRecord, tmp_path: Path) -> None:
    consumed: list[int] = []

    def source() -> Iterator[OGCRecord]:
        for index in range(12):
            consumed.append(index)
            changed = record.clone()
            changed.id = str(index)
            yield changed

    reader = records_to_arrow(source(), batch_size=2)
    assert consumed == []
    first = next(reader)
    assert consumed == [0, 1]
    assert first["id"].to_pylist() == ["0", "1"]
    remaining = pa.RecordBatchReader.from_batches(reader.schema, reader)
    path = tmp_path / "ordered.parquet"
    to_parquet(remaining, path)
    assert [document.id for document in read_parquet(path)] == [
        str(index) for index in range(2, 12)
    ]
    assert consumed == list(range(12))


def test_projection_edits_do_not_change_original_payload(record: OGCRecord) -> None:
    table = records_to_arrow([record]).read_all()
    index = table.schema.get_field_index("properties.title")
    edited = table.set_column(index, table.schema.field(index), pa.array(["Edited projection"]))
    assert [item.to_dict(transform_hrefs=False) for item in arrow_to_records(edited)] == [
        record.to_dict(transform_hrefs=False)
    ]


def test_input_is_not_mutated_and_exports_are_independent(record: OGCRecord) -> None:
    before = _canonical([record])
    original_created = record.properties["created"]
    table = records_to_arrow([record]).read_all()
    exported = list(arrow_to_records(table))
    exported[0].extra_fields["new"] = "value"
    assert _canonical([record]) == before
    assert record.properties["created"] == original_created
    assert [item.to_dict(transform_hrefs=False) for item in arrow_to_records(table)] == [
        record.to_dict(transform_hrefs=False)
    ]


def test_parquet_failure_preserves_existing_destination(record: OGCRecord, tmp_path: Path) -> None:
    path = tmp_path / "records.parquet"
    to_parquet(records_to_arrow([record]), path)
    original = path.read_bytes()
    invalid = record.clone()
    invalid.geometry = {"type": "Unknown", "coordinates": []}
    with pytest.raises(ValueError, match="geometry"):
        to_parquet(records_to_arrow([record, invalid], batch_size=1), path)
    assert path.read_bytes() == original
    assert not list(tmp_path.glob(".records-parquet-*"))
