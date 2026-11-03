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

import pyarrow.parquet as pq
import pytest
from pystac.extensions.ogc_record import OGCRecord
from shapely import from_wkb

from ogc_records_parquet import (
    JSONObject,
    arrow_to_records,
    read_parquet,
    records_to_arrow,
    to_parquet,
)


@pytest.mark.parametrize(
    "geometry",
    [
        None,
        {"type": "Point", "coordinates": [1, 2]},
        {"type": "Point", "coordinates": [1, 2, 3]},
        {"type": "LineString", "coordinates": [[0, 1], [3, 4]]},
        {"type": "Polygon", "coordinates": []},
        {"type": "GeometryCollection", "geometries": [{"type": "Point", "coordinates": [1, 2]}]},
        {"type": "Point", "coordinates": [1, 2], "foreign": {"value": []}},
    ],
)
def test_geometry_and_original_bbox_roundtrip(
    record: OGCRecord, geometry: JSONObject | None, tmp_path: Path
) -> None:
    document = record.clone()
    document.geometry = geometry
    document.bbox = [0, 1, 2, 3, 4, 5]
    table = records_to_arrow([document]).read_all()
    path = tmp_path / "geometry.parquet"
    to_parquet(table, path)
    assert [item.to_dict(transform_hrefs=False) for item in read_parquet(path)] == [
        document.to_dict(transform_hrefs=False)
    ]


def test_geometry_covering_uses_geometry_and_preserves_original_bbox(record: OGCRecord) -> None:
    record.geometry = {"type": "Point", "coordinates": [1, 2, 3]}
    record.bbox = [100, 200, 300, 400]
    table = records_to_arrow([record]).read_all()
    assert table["bbox"].to_pylist() == [{"xmin": 1.0, "ymin": 2.0, "xmax": 1.0, "ymax": 2.0}]
    assert from_wkb(table["geometry"][0].as_py()).has_z
    assert [item.to_dict(transform_hrefs=False) for item in arrow_to_records(table)] == [
        record.to_dict(transform_hrefs=False)
    ]


def test_null_and_empty_geometries_have_null_covering(record: OGCRecord) -> None:
    empty = OGCRecord(id="empty", geometry={"type": "Polygon", "coordinates": []})
    table = records_to_arrow([record, empty], batch_size=1).read_all()
    assert table["bbox"].null_count == table.num_rows
    assert table["geometry"].null_count == 1


def test_geoparquet_and_geoarrow_metadata_are_consistent(record: OGCRecord, tmp_path: Path) -> None:
    path = tmp_path / "geo.parquet"
    to_parquet(records_to_arrow([record]), path)
    schema = pq.read_schema(path)
    geo = json.loads(schema.metadata[b"geo"])
    geometry = geo["columns"]["geometry"]
    field_metadata = schema.field("geometry").metadata
    assert field_metadata is not None
    extension = json.loads(field_metadata[b"ARROW:extension:metadata"])
    assert geo["version"] == "1.1.0"
    assert geo["primary_column"] == "geometry"
    assert geometry["encoding"] == "WKB"
    assert geometry["crs"] == extension["crs"]
    assert geometry["crs"]["id"] == {"authority": "OGC", "code": "CRS84"}
    assert geometry["covering"]["bbox"]["xmin"] == ["bbox", "xmin"]
    assert field_metadata[b"ARROW:extension:name"] == b"geoarrow.wkb"
