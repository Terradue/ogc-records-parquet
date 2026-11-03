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
    from ogc_records_parquet import JSONValue

import pytest

from ogc_records_parquet._json import require_json_object


def test_validation_retains_document_and_nested_containers() -> None:
    values: list[JSONValue] = [None, True, 1, 1.5, "text", {}]
    nested = {"values": values}
    document = {"nested": nested}

    validated = require_json_object(document)

    assert validated is document
    assert document == {"nested": {"values": [None, True, 1, 1.5, "text", {}]}}
    assert document["nested"] is nested
    assert nested["values"] is values


@pytest.mark.parametrize("value", [None, [], "text", 1, True])
def test_validation_requires_an_object(value: object) -> None:
    with pytest.raises(ValueError, match="Expected a JSON object"):
        require_json_object(value)
