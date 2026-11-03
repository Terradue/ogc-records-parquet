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

from pathlib import Path

import pytest
from pystac.extensions.ogc_record import OGCRecord


@pytest.fixture
def record() -> OGCRecord:
    return OGCRecord(
        id="application",
        properties={
            "type": "service",
            "title": "A workflow",
            "created": "2026-01-01T12:13:14.123456789+00:00",
            "keywords": [],
        },
    )


@pytest.fixture
def example_records() -> list[OGCRecord]:
    paths = sorted(
        (Path(__file__).parents[1] / "examples" / "ogc-records").glob("*/records/*.json")
    )
    return [OGCRecord.from_file(path) for path in paths]
