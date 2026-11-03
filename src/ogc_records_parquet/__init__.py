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

"""Store PySTAC OGCRecord objects alongside Arrow and GeoParquet query projections.

Use `records_to_arrow()` and `to_parquet()` to write records, then
`read_parquet()` to reconstruct them. `arrow_to_records()` reconstructs records
from an in-memory table or stream. Readers use the preserved JSON payload,
independently of query columns and storage-only collection membership.

Record parsing and serialization belong to `pystac-ext-ogc-record`. This package
checks storage compatibility and projection safety; OGC profile validation and
query execution remain the caller's responsibility.
"""

from ogc_records_parquet.__about__ import __version__
from ogc_records_parquet._json import JSONObject, JSONValue
from ogc_records_parquet._schema import default_schema
from ogc_records_parquet.arrow import arrow_to_records, records_to_arrow
from ogc_records_parquet.parquet import (
    read_collection_ids,
    read_collections,
    read_metadata,
    read_parquet,
    to_parquet,
)

__all__ = [
    "JSONObject",
    "JSONValue",
    "__version__",
    "arrow_to_records",
    "default_schema",
    "read_collection_ids",
    "read_collections",
    "read_metadata",
    "read_parquet",
    "records_to_arrow",
    "to_parquet",
]
