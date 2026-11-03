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
from unittest.mock import patch

import pytest
import requests
from click import UsageError
from click.testing import CliRunner
from pystac.extensions.ogc_record import OGCRecord

from ogc_records_parquet import read_parquet
from ogc_records_parquet.cli import main

if TYPE_CHECKING:
    from pathlib import Path


@pytest.mark.parametrize("arguments", [[], ["record.json"], ["--output", "out.parquet"]])
def test_missing_required_arguments(arguments: list[str]) -> None:
    result = CliRunner().invoke(main, arguments)
    assert result.exit_code == UsageError.exit_code
    assert "Missing" in result.output


def test_help() -> None:
    result = CliRunner().invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "--output" in result.output
    assert "OAUTH2_BEARER" in result.output
    assert "REGISTRY_AUTH_FILE" in result.output


def test_local_records_preserve_order_and_create_parent(tmp_path: Path) -> None:
    records = [OGCRecord(id="first"), OGCRecord(id="second")]
    sources = [tmp_path / "first.json", tmp_path / "second.json"]
    for record, source in zip(records, sources, strict=True):
        record.save_object(dest_href=str(source))
    output = tmp_path / "nested" / "records.parquet"
    result = CliRunner().invoke(main, [str(path) for path in sources] + ["--output", str(output)])
    assert result.exit_code == 0, result.output
    assert [record.id for record in read_parquet(output)] == ["first", "second"]


@pytest.mark.parametrize(
    "source", ["https://example.org/record.json", "oci://registry.example/record:latest"]
)
def test_remote_record(source: str, record: OGCRecord, tmp_path: Path) -> None:
    output = tmp_path / "records.parquet"
    with patch("ogc_records_parquet.cli.requests.Session.get") as get:
        get.return_value.json.return_value = record.to_dict()
        result = CliRunner().invoke(main, [source, "--output", str(output)])
    assert result.exit_code == 0, result.output
    get.assert_called_once_with(source)
    assert next(read_parquet(output)).to_dict() == record.to_dict()


@pytest.mark.parametrize("error", [requests.HTTPError("unavailable"), ValueError("invalid JSON")])
def test_read_failure_does_not_create_output(error: Exception, tmp_path: Path) -> None:
    output = tmp_path / "records.parquet"
    with patch("ogc_records_parquet.cli.requests.Session.get", side_effect=error):
        result = CliRunner().invoke(
            main, ["https://example.org/record.json", "--output", str(output)]
        )
    assert result.exit_code == 1
    assert not output.exists()


def test_write_failure(record: OGCRecord, tmp_path: Path) -> None:
    with (
        patch("ogc_records_parquet.cli.requests.Session.get") as get,
        patch("ogc_records_parquet.cli.to_parquet", side_effect=OSError("write failed")),
    ):
        get.return_value.json.return_value = record.to_dict()
        result = CliRunner().invoke(
            main, ["https://example.org/record.json", "--output", str(tmp_path / "out.parquet")]
        )
    assert result.exit_code == 1


@pytest.mark.parametrize(
    "platform,runtime,relative",
    [
        ("linux", "/run/example", "containers/auth.json"),
        ("linux", "", ".config/containers/auth.json"),
        ("darwin", "/run/example", ".config/containers/auth.json"),
    ],
)
def test_authfile_default_at_invocation(
    platform: str, runtime: str, relative: str, tmp_path: Path
) -> None:
    with (
        patch("ogc_records_parquet.cli.sys.platform", platform),
        patch("ogc_records_parquet.cli.Path.home", return_value=tmp_path),
        patch("ogc_records_parquet.cli.ContainersAuth") as auth,
        patch("ogc_records_parquet.cli.Path.exists", return_value=True),
        patch("ogc_records_parquet.cli.OCIAdapter"),
        patch("ogc_records_parquet.cli.requests.Session.get", side_effect=OSError("stop")),
    ):
        CliRunner().invoke(
            main,
            ["record.json", "--output", str(tmp_path / "out.parquet")],
            env={"XDG_RUNTIME_DIR": runtime, "REGISTRY_AUTH_FILE": None},
        )
    base = type(tmp_path)(runtime) if platform == "linux" and runtime else tmp_path
    auth.get_instance.assert_called_once_with(base / relative)


def test_credentials_from_environment(record: OGCRecord, tmp_path: Path) -> None:
    authfile = tmp_path / "auth.json"
    authfile.write_text("{}")
    with (
        patch("ogc_records_parquet.cli.ContainersAuth") as auth,
        patch("ogc_records_parquet.cli.OCIAdapter"),
        patch("ogc_records_parquet.cli.BearerAuthHTTPAdapter") as bearer,
        patch("ogc_records_parquet.cli.requests.Session.get") as get,
    ):
        get.return_value.json.return_value = record.to_dict()
        result = CliRunner().invoke(
            main,
            ["https://example.org/record.json", "--output", str(tmp_path / "out.parquet")],
            env={
                "REGISTRY_AUTH_FILE": str(authfile),
                "OCI_HOSTNAME": "registry.example",
                "OCI_USERNAME": "test-user",
                "OCI_PASSWORD": "test-credential",
                "OAUTH2_BEARER": "test-token",
            },
        )
    assert result.exit_code == 0, result.output
    auth.get_instance.assert_called_once_with(authfile)
    auth.get_instance.return_value.add_auth.assert_called_once_with(
        "registry.example", "test-user", "test-credential"
    )
    bearer.assert_called_once_with("test-token")


def test_file_url(record: OGCRecord, tmp_path: Path) -> None:
    source = tmp_path / "record.json"
    record.save_object(dest_href=str(source))
    output = tmp_path / "output.parquet"
    result = CliRunner().invoke(main, [source.as_uri(), "--output", str(output)])
    assert result.exit_code == 0, result.output
    assert next(read_parquet(output)).id == record.id
