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

"""Validate JSON storage boundaries without copying or modeling Record documents."""

from __future__ import annotations

import json
import math
from typing import TypeAlias, TypeGuard

JSONValue: TypeAlias = bool | int | float | str | list["JSONValue"] | dict[str, "JSONValue"] | None
"""Recursive type alias for JSON scalars, lists, objects, and null.

This alias describes generic JSON values, not an OGC Record schema. Storage
validation additionally rejects non-finite floats; annotations alone cannot
express that constraint. Tuples and non-string object keys are not accepted.
"""

JSONObject: TypeAlias = dict[str, JSONValue]
"""Type alias for a JSON object with string keys and recursively JSON-compatible values.

Used for decoded file metadata and catalog descriptions. It is not a Record
model or a validation function; use `OGCRecord` for record manipulation.
"""


def _is_json_value(value: object) -> TypeGuard[JSONValue]:
    """Check recursively for finite JSON values without copying containers."""
    if value is None or isinstance(value, (str, bool, int)):
        return True
    if isinstance(value, float):
        return math.isfinite(value)
    if isinstance(value, list):
        return all(_is_json_value(element) for element in value)
    if isinstance(value, dict):
        return all(
            isinstance(name, str) and _is_json_value(element) for name, element in value.items()
        )
    return False


def require_json_object(value: object) -> JSONObject:
    """Validate a storage document and return it without copying or modifying it.

    The caller retains ownership of the document and its nested values.

    Raises:
        ValueError: If the input is not an object, contains non-JSON or non-finite
            values, or has non-string keys.
    """
    if not _is_json_value(value):
        raise ValueError("JSON objects require finite JSON values and string keys")
    if not isinstance(value, dict):
        raise ValueError("Expected a JSON object")
    return value


def loads_object(payload: str | bytes) -> JSONObject:
    """Decode a JSON object and reject duplicate keys and non-finite values."""
    return require_json_object(json.loads(payload, object_pairs_hook=_unique_object))


def _unique_object(pairs: list[tuple[str, JSONValue]]) -> JSONObject:
    result: JSONObject = {}
    for name, value in pairs:
        if name in result:
            raise ValueError(f"Duplicate JSON key: {name}")
        result[name] = value
    return result
