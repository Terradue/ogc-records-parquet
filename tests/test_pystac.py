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

import pytest
from pystac import Asset, Link, StacIO
from pystac.extensions.ogc_record import OGCRecord

from ogc_records_parquet import arrow_to_records, read_parquet, records_to_arrow, to_parquet


def test_pystac_file_and_metadata_apis_roundtrip(record: OGCRecord, tmp_path: Path) -> None:
    record.title = "São Paulo 🌍"
    record.add_link(Link("related", "https://example.org/record", title="Related record"))
    record.add_asset("workflow", Asset("https://example.org/workflow.cwl", roles=["data"]))
    record.time = {"interval": ["2020-01-01", ".."]}
    record.conforms_to = ["https://example.org/profile"]
    source = tmp_path / "record.json"
    record.save_object(dest_href=str(source))
    loaded = OGCRecord.from_file(source)
    destination = tmp_path / "records.parquet"
    to_parquet(records_to_arrow([loaded]), destination)
    restored = next(read_parquet(destination))
    assert isinstance(restored, OGCRecord)
    assert restored.to_dict(transform_hrefs=False) == loaded.to_dict(transform_hrefs=False)
    assert restored.title == record.title
    assert restored.assets["workflow"].owner is restored
    related = restored.get_single_link("related")
    assert related is not None
    assert related.title == "Related record"
    restored.title = "Edited through the extension"
    exported = tmp_path / "export.json"
    restored.save_object(dest_href=str(exported))
    assert OGCRecord.from_file(exported).title == "Edited through the extension"


def test_relative_links_are_not_rewritten_by_parquet(record: OGCRecord, tmp_path: Path) -> None:
    record.set_self_href(str(tmp_path / "source.json"))
    record.add_link(Link("related", "../related.json"))
    record.add_asset("data", Asset("./data.csv"))
    table = records_to_arrow([record]).read_all()
    restored = next(arrow_to_records(table))
    assert restored.to_dict(transform_hrefs=False) == record.to_dict(transform_hrefs=False)
    assert restored.assets["data"].href == "./data.csv"
    related = restored.get_single_link("related")
    assert related is not None
    assert related.get_href(transform_href=False) == "../related.json"


@pytest.mark.parametrize("value", [float("nan"), float("inf"), {1: "value"}, (1, 2), object()])
def test_rejects_non_json_record_metadata(record: OGCRecord, value: object) -> None:
    record.extra_fields["custom"] = {"nested": [value]}
    with pytest.raises(ValueError):
        records_to_arrow([record]).read_all()


def test_serialization_failure_preserves_existing_file(record: OGCRecord, tmp_path: Path) -> None:
    path = tmp_path / "records.parquet"
    to_parquet(records_to_arrow([record]), path)
    original = path.read_bytes()
    invalid = record.clone()
    invalid.extra_fields["custom"] = float("nan")
    with pytest.raises(ValueError, match="finite"):
        to_parquet(records_to_arrow([record, invalid], batch_size=1), path)
    assert path.read_bytes() == original


def test_pystac_read_json_preserves_source_links(record: OGCRecord, tmp_path: Path) -> None:
    path = tmp_path / "record.json"
    record.save_object(dest_href=str(path))
    loaded = OGCRecord.from_dict(StacIO.default().read_json(str(path)))
    table = records_to_arrow([loaded]).read_all()
    restored = next(arrow_to_records(table))
    assert restored.get_self_href() is None
    assert restored.to_dict() == record.to_dict()
