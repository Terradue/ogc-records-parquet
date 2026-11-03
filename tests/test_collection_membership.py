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

"""Verify storage membership independently of descriptions and original Record JSON."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterator

import json
from pathlib import Path

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq
import pytest
from pystac.extensions.ogc_record import OGCRecord

from ogc_records_parquet import (
    JSONObject,
    arrow_to_records,
    default_schema,
    read_collection_ids,
    read_collections,
    read_metadata,
    read_parquet,
    records_to_arrow,
    to_parquet,
)

EXAMPLES = Path(__file__).parents[1] / "examples" / "ogc-records"
COLLECTION_IDS = ("hazard-mapping", "earth-observation-processing")


def _catalogs() -> JSONObject:
    result: JSONObject = {}
    for identifier in COLLECTION_IDS:
        result[identifier] = json.loads((EXAMPLES / identifier / "collection.json").read_text())
    return result


@pytest.mark.parametrize("collection_ids", [(COLLECTION_IDS[0],), COLLECTION_IDS])
def test_real_collection_metadata_and_json_roundtrip(
    tmp_path: Path, collection_ids: tuple[str, ...]
) -> None:
    catalogs = {identifier: _catalogs()[identifier] for identifier in collection_ids}
    records = [
        record
        for identifier in collection_ids
        for path in sorted((EXAMPLES / identifier / "records").glob("*.json"))
        for record in [OGCRecord.from_file(path)]
    ]
    assert all(record.collection_id is None for record in records)
    path = tmp_path / "records.parquet"
    memberships = [
        identifier
        for identifier in collection_ids
        for _ in sorted((EXAMPLES / identifier / "records").glob("*.json"))
    ]
    to_parquet(
        records_to_arrow(records, collections=catalogs, collection_ids=memberships, batch_size=3),
        path,
    )
    assert list(read_collection_ids(path)) == memberships
    assert read_collections(path) == catalogs
    assert [item.to_dict(transform_hrefs=False) for item in read_parquet(path)] == [
        item.to_dict(transform_hrefs=False) for item in records
    ]
    assert "collection" not in pq.read_schema(path).names
    assert list(tmp_path.iterdir()) == [path]


def test_legacy_mixed_collections_cannot_be_selected_by_persisted_membership(
    tmp_path: Path,
) -> None:
    groups = {
        identifier: [
            record
            for path in sorted((EXAMPLES / identifier / "records").glob("*.json"))
            for record in [OGCRecord.from_file(path)]
        ]
        for identifier in COLLECTION_IDS
    }
    assert {identifier: len(records) for identifier, records in groups.items()} == {
        "hazard-mapping": 4,
        "earth-observation-processing": 7,
    }
    records = [record for group in groups.values() for record in group]
    path = tmp_path / "mixed.parquet"
    table = _legacy_table(records)
    pq.write_table(table, path)
    table = pq.read_table(path)
    assert [item.to_dict(transform_hrefs=False) for item in read_parquet(path)] == [
        item.to_dict(transform_hrefs=False) for item in records
    ]
    assert list(read_collection_ids(path)) == [None] * len(records)
    assert read_collections(path) == _catalogs()
    with pytest.raises(KeyError, match="collection"):
        table.column("collection")
    with pytest.raises(KeyError, match="__collection_id"):
        table.column("__collection_id")


@pytest.mark.parametrize("membership", [None, "hazard-mapping", "unknown"])
@pytest.mark.parametrize("project_membership", [False, True])
def test_synthetic_membership_values_are_preserved_but_not_validated(
    tmp_path: Path, record: OGCRecord, membership: str | None, project_membership: bool
) -> None:
    # These synthetic fields are not an EOAP profile or a storage-only membership API.
    record.collection_id = membership
    projections = default_schema()
    if project_membership:
        projections = projections.append(pa.field("collection", pa.string()))
    path = tmp_path / "membership.parquet"
    to_parquet(records_to_arrow([record], schema=projections, collections=_catalogs()), path)
    assert [item.to_dict(transform_hrefs=False) for item in read_parquet(path)] == [
        record.to_dict(transform_hrefs=False)
    ]
    assert list(read_collection_ids(path)) == [None]
    table = pq.read_table(path)
    if project_membership:
        assert table.column("collection").to_pylist() == [membership]
    else:
        assert "collection" not in table.schema.names


@pytest.mark.parametrize("catalogs", [{}, {"wrong-key": {"id": "different-id"}}])
def test_synthetic_absent_description_and_metadata_id_mismatch_are_accepted(
    tmp_path: Path, record: OGCRecord, catalogs: JSONObject
) -> None:
    record.collection_id = "absent"
    path = tmp_path / "unchecked.parquet"
    to_parquet(records_to_arrow([record], collections=catalogs, collection_ids=["absent"]), path)
    assert list(read_collection_ids(path)) == ["absent"]
    assert read_collections(path) == catalogs
    assert [item.to_dict(transform_hrefs=False) for item in read_parquet(path)] == [
        record.to_dict(transform_hrefs=False)
    ]


def test_synthetic_duplicate_ids_in_different_collections_survive(tmp_path: Path) -> None:
    source = OGCRecord.from_file(
        EXAMPLES / "hazard-mapping/records/diachronic-flood-detection.json"
    )
    records = [source.clone() for _ in COLLECTION_IDS]
    for item, identifier in zip(records, COLLECTION_IDS, strict=True):
        item.collection_id = identifier
    projections = default_schema().append(pa.field("collection", pa.string()))
    path = tmp_path / "duplicates.parquet"
    to_parquet(records_to_arrow(records, schema=projections, collections=_catalogs()), path)
    assert [item.to_dict(transform_hrefs=False) for item in read_parquet(path)] == [
        item.to_dict(transform_hrefs=False) for item in records
    ]
    table = pq.read_table(path)
    for identifier in COLLECTION_IDS:
        selected = table.filter(pc.equal(table.column("collection"), pa.scalar(identifier)))
        assert selected.column("id").to_pylist() == [source.id]


def test_metadata_does_not_assign_membership_to_original_records(
    tmp_path: Path, example_records: list[OGCRecord]
) -> None:
    projections = default_schema().append(pa.field("collection", pa.string()))
    path = tmp_path / "unassigned.parquet"
    to_parquet(records_to_arrow(example_records, schema=projections, collections=_catalogs()), path)
    table = pq.read_table(path)
    assert table.column("collection").null_count == len(example_records)
    assert [item.to_dict(transform_hrefs=False) for item in read_parquet(path)] == [
        item.to_dict(transform_hrefs=False) for item in example_records
    ]
    assert all(record.collection_id is None for record in read_parquet(path))


def _legacy_table(records: list[OGCRecord]) -> pa.Table:
    """Build a format 1.0.0 fixture with the historical metadata and columns."""
    table = records_to_arrow(records, collections=_catalogs()).read_all().drop(["__collection_id"])
    metadata = dict(table.schema.metadata or {})
    document = json.loads(metadata[b"ogc-records-parquet"])
    document["version"] = "1.0.0"
    document["writer_version"] = "0.1.0"
    document.pop("membership_column")
    metadata[b"ogc-records-parquet"] = json.dumps(document).encode()
    return table.replace_schema_metadata(metadata)


@pytest.mark.parametrize("batch_size", [1, 3, 20])
def test_real_explicit_membership_selects_four_and_seven(tmp_path: Path, batch_size: int) -> None:
    records: list[OGCRecord] = []
    memberships: list[str | None] = []
    for identifier in COLLECTION_IDS:
        for path in sorted((EXAMPLES / identifier / "records").glob("*.json")):
            for record in [OGCRecord.from_file(path)]:
                records.append(record)
                memberships.append(identifier)
    table = records_to_arrow(
        iter(records),
        collection_ids=iter(memberships),
        collections=_catalogs(),
        batch_size=batch_size,
    ).read_all()
    assert table.column("__collection_id").to_pylist() == memberships
    assert [item.to_dict(transform_hrefs=False) for item in arrow_to_records(table)] == [
        item.to_dict(transform_hrefs=False) for item in records
    ]
    path = tmp_path / "eleven.parquet"
    to_parquet(table, path)
    assert list(read_collection_ids(path, batch_size=batch_size)) == memberships
    assert read_collections(path) == _catalogs()
    assert [item.to_dict(transform_hrefs=False) for item in read_parquet(path)] == [
        item.to_dict(transform_hrefs=False) for item in records
    ]
    expected_counts = {"hazard-mapping": 4, "earth-observation-processing": 7}
    persisted = pq.read_table(path)
    for identifier, count in expected_counts.items():
        selected = persisted.filter(
            pc.equal(persisted.column("__collection_id"), pa.scalar(identifier))
        )
        expected = [
            record
            for record, membership in zip(records, memberships, strict=True)
            if membership == identifier
        ]
        assert selected.num_rows == count
        assert [item.to_dict(transform_hrefs=False) for item in arrow_to_records(selected)] == [
            item.to_dict(transform_hrefs=False) for item in expected
        ]


@pytest.mark.parametrize("memberships", [None, [None, "unknown", None]])
def test_unknown_or_partial_membership_is_independent_of_metadata(
    tmp_path: Path, record: OGCRecord, memberships: list[str | None] | None
) -> None:
    records = [record] * 3
    expected = [None] * len(records) if memberships is None else memberships
    path = tmp_path / "partial.parquet"
    to_parquet(
        records_to_arrow(
            records, collection_ids=memberships, collections=_catalogs(), batch_size=1
        ),
        path,
    )
    assert list(read_collection_ids(path)) == expected
    assert [item.to_dict(transform_hrefs=False) for item in read_parquet(path)] == [
        item.to_dict(transform_hrefs=False) for item in records
    ]
    assert read_collections(path) == _catalogs()
    assert read_metadata(path)["version"] == "1.1.0"
    assert read_metadata(path)["membership_column"] == "__collection_id"


@pytest.mark.parametrize("invalid", ["", 1, False, [], {}])
def test_invalid_membership_values_are_rejected(record: OGCRecord, invalid: str | None) -> None:
    # Pytest supplies deliberately invalid runtime values without weakening the public API type.
    with pytest.raises(ValueError, match="membership"):
        records_to_arrow([record], collection_ids=[invalid]).read_all()


@pytest.mark.parametrize(
    "record_count, memberships", [(1, []), (1, ["a", "b"]), (0, ["a"]), (3, ["a", "b"])]
)
def test_membership_length_mismatches_fail_atomically(
    tmp_path: Path, record: OGCRecord, record_count: int, memberships: list[str | None]
) -> None:
    path = tmp_path / "length.parquet"
    path.write_bytes(b"existing file")
    with pytest.raises(ValueError, match="zip"):
        to_parquet(
            records_to_arrow(
                [record] * record_count, collection_ids=iter(memberships), batch_size=1
            ),
            path,
        )
    assert path.read_bytes() == b"existing file"


def test_duplicate_ids_use_explicit_membership_not_original_fields(
    tmp_path: Path, record: OGCRecord
) -> None:
    original = record.clone()
    original.collection_id = "original"
    original.extra_fields["__collection_id"] = "original-extension"
    table = records_to_arrow(
        [original, original], collection_ids=COLLECTION_IDS, schema=pa.schema([])
    ).read_all()
    assert table.column("__collection_id").to_pylist() == list(COLLECTION_IDS)
    assert [item.to_dict(transform_hrefs=False) for item in arrow_to_records(table)] == [
        original.to_dict(transform_hrefs=False),
        original.to_dict(transform_hrefs=False),
    ]
    changed = table.set_column(
        table.schema.get_field_index("__collection_id"),
        pa.field("__collection_id", pa.string()),
        pa.array(["other", None]),
    )
    assert [item.to_dict(transform_hrefs=False) for item in arrow_to_records(changed)] == [
        original.to_dict(transform_hrefs=False),
        original.to_dict(transform_hrefs=False),
    ]
    path = tmp_path / "duplicates.parquet"
    to_parquet(changed, path)
    assert list(read_collection_ids(path)) == ["other", None]
    assert [item.to_dict(transform_hrefs=False) for item in read_parquet(path)] == [
        original.to_dict(transform_hrefs=False),
        original.to_dict(transform_hrefs=False),
    ]


@pytest.mark.parametrize("schema", [None, pa.schema([]), pa.schema([pa.field("id", pa.string())])])
def test_reserved_membership_is_added_to_every_projection_schema(
    record: OGCRecord, schema: pa.Schema | None
) -> None:
    table = records_to_arrow([record], schema=schema, collection_ids=["absent"]).read_all()
    assert table.schema.field("__collection_id") == pa.field("__collection_id", pa.string())
    assert table.column("__collection_id").to_pylist() == ["absent"]
    assert [item.to_dict(transform_hrefs=False) for item in arrow_to_records(table)] == [
        record.to_dict(transform_hrefs=False)
    ]


def test_membership_projection_conflict_is_rejected() -> None:
    with pytest.raises(ValueError, match="reserved"):
        records_to_arrow([], schema=pa.schema([pa.field("__collection_id", pa.string())]))


@pytest.mark.parametrize("damage", ["missing", "type", "nullable", "declaration"])
def test_new_format_requires_valid_membership_storage(
    tmp_path: Path, record: OGCRecord, damage: str
) -> None:
    table = records_to_arrow([record]).read_all()
    index = table.schema.get_field_index("__collection_id")
    if damage == "missing":
        table = table.drop(["__collection_id"])
    elif damage == "type":
        table = table.set_column(index, "__collection_id", pa.array([1]))
    elif damage == "nullable":
        table = table.set_column(
            index, pa.field("__collection_id", pa.string(), nullable=False), pa.array(["a"])
        )
    else:
        metadata = dict(table.schema.metadata or {})
        document = json.loads(metadata[b"ogc-records-parquet"])
        document["membership_column"] = "other"
        metadata[b"ogc-records-parquet"] = json.dumps(document).encode()
        table = table.replace_schema_metadata(metadata)
    path = tmp_path / "damaged.parquet"
    with pytest.raises(ValueError, match="membership"):
        to_parquet(table, path)
    pq.write_table(table, path)
    with pytest.raises(ValueError, match="membership"):
        list(read_collection_ids(path))
    with pytest.raises(ValueError, match="membership"):
        list(read_parquet(path))


@pytest.mark.parametrize("batch_size", [0, -1])
def test_membership_reader_rejects_invalid_batch_size(tmp_path: Path, batch_size: int) -> None:
    with pytest.raises(ValueError, match="batch_size"):
        list(read_collection_ids(tmp_path / "missing.parquet", batch_size=batch_size))


def test_empty_membership_streams_and_legacy_arrow(record: OGCRecord, tmp_path: Path) -> None:
    table = records_to_arrow([], collection_ids=[]).read_all()
    path = tmp_path / "empty.parquet"
    to_parquet(table, path)
    assert list(read_collection_ids(path)) == []
    assert list(read_parquet(path)) == []
    legacy = _legacy_table([record])
    assert [item.to_dict(transform_hrefs=False) for item in arrow_to_records(legacy)] == [
        record.to_dict(transform_hrefs=False)
    ]


def test_payload_only_arrow_projection_still_reconstructs(record: OGCRecord) -> None:
    table = records_to_arrow([record], collection_ids=["storage-only"]).read_all()
    assert [
        item.to_dict(transform_hrefs=False)
        for item in arrow_to_records(table.select(["__record_json"]))
    ] == [record.to_dict(transform_hrefs=False)]


def test_legacy_membership_like_projection_is_not_interpreted(
    tmp_path: Path, record: OGCRecord
) -> None:
    legacy = _legacy_table([record]).append_column("__collection_id", pa.array(["untrusted"]))
    path = tmp_path / "legacy-projection.parquet"
    pq.write_table(legacy, path)
    assert list(read_collection_ids(path)) == [None]
    assert [item.to_dict(transform_hrefs=False) for item in read_parquet(path)] == [
        record.to_dict(transform_hrefs=False)
    ]


def test_membership_consumption_is_lazy_and_keeps_batch_alignment(record: OGCRecord) -> None:
    events: list[str] = []

    def memberships() -> Iterator[str | None]:
        for membership in ["first", None, "third"]:
            events.append(str(membership))
            yield membership

    reader = records_to_arrow([record] * 3, collection_ids=memberships(), batch_size=1)
    assert events == []
    assert reader.read_next_batch().column("__collection_id").to_pylist() == ["first"]
    assert events == ["first"]
    assert reader.read_all().column("__collection_id").to_pylist() == [None, "third"]


def test_invalid_later_membership_keeps_existing_file(tmp_path: Path, record: OGCRecord) -> None:
    path = tmp_path / "late-error.parquet"
    path.write_bytes(b"existing")
    with pytest.raises(ValueError, match="membership"):
        to_parquet(records_to_arrow([record] * 2, collection_ids=["valid", ""], batch_size=1), path)
    assert path.read_bytes() == b"existing"
