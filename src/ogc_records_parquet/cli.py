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

"""Import local or remote OGC Record JSON documents into one GeoParquet file.

The optional CLI dependencies provide HTTP bearer authentication and OCI registry
access. Each input must contain one record, parsed through PySTAC.
"""

from __future__ import annotations

import os
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import click
import requests
from loguru import logger
from pystac.extensions.ogc_record import OGCRecord
from requests.adapters import BaseAdapter, HTTPAdapter
from session_adapters.bearer_auth_http_adapter import BearerAuthHTTPAdapter
from session_adapters.conainers_auth import ContainersAuth
from session_adapters.file_adapter import FileAdapter
from session_adapters.oci_adapter import OCIAdapter

from .arrow import records_to_arrow
from .parquet import to_parquet


def _default_authfile() -> Path:
    """Resolve the platform default registry credentials path at invocation time."""
    # Windows / macOS
    base_dir = Path.home() / ".config"

    if sys.platform == "linux":
        runtime_dir = os.environ.get("XDG_RUNTIME_DIR")
        if runtime_dir:
            base_dir = Path(runtime_dir)

    return base_dir / "containers" / "auth.json"


def _read_records(session: requests.Session, sources: tuple[str, ...]) -> list[OGCRecord]:
    """Read individual record documents in order using the configured transports.

    Relative paths are resolved from the working directory. HTTP and parsing
    errors propagate to the command's diagnostic boundary.
    """
    records: list[OGCRecord] = []
    for source in sources:
        try:
            parsed = urlparse(source)
            is_url = f"{parsed.scheme}://" in session.adapters and (
                bool(parsed.netloc) or parsed.scheme == "file"
            )
        except ValueError:
            is_url = False
        location = source if is_url else Path(source).absolute().as_uri()
        logger.debug(f"Reading OGC Record from {location}...")
        response = session.get(location)
        response.raise_for_status()
        records.append(OGCRecord.from_dict(response.json()))
        logger.success(f"OGC Record successfully parsed from {location}.")
    return records


@click.command()
@click.argument("ogcrecords", nargs=-1, required=True)
@click.option(
    "--output",
    type=click.Path(path_type=Path),
    required=True,
    help="Destination GeoParquet file; parent directories are created.",
)
@click.option("--oci-hostname", envvar="OCI_HOSTNAME", show_envvar=True)
@click.option("--oci-username", envvar="OCI_USERNAME", show_envvar=True)
@click.option("--oci-password", envvar="OCI_PASSWORD", show_envvar=True)
@click.option(
    "--authfile",
    help="Path of the managed registry credentials file",
    envvar="REGISTRY_AUTH_FILE",
    show_envvar=True,
    default=_default_authfile,
    show_default=True,
    required=False,
    type=click.Path(path_type=Path),
)
@click.option("--oauth2-bearer", envvar="OAUTH2_BEARER", show_envvar=True)
# Click passes each declared option as a separate callback argument.
def main(  # noqa: PLR0913 -- Click supplies one argument per declared option.
    ogcrecords: tuple[str, ...],
    *,
    output: Path,
    oci_hostname: str | None = None,
    oci_username: str | None = None,
    oci_password: str | None = None,
    authfile: Path | None,
    oauth2_bearer: str | None = None,
) -> None:
    """Convert one or more OGC Record JSON sources into a GeoParquet file.

    Sources may be local paths or HTTP, HTTPS, file, or OCI URLs. Records are
    stored in argument order. Parent directories are created and an existing
    output file is overwritten. All input records are loaded before writing.

    Args:
        ogcrecords: Sources containing one OGC Record JSON object each.
        output: Destination GeoParquet path.
        oci_hostname: Registry host for explicit credentials; requires both
            username and password to take effect.
        oci_username: Registry username.
        oci_password: Registry password.
        authfile: Registry credentials file; missing files use empty credentials.
        oauth2_bearer: Bearer token applied to HTTP and HTTPS requests.

    Raises:
        SystemExit: With status 1 if reading, parsing, or writing fails.
    """
    session = requests.Session()

    def _mount_session(scheme: str, adapter: BaseAdapter) -> None:
        logger.debug(f"Mounting '{scheme}' scheme to '{type(adapter).__name__}'...")
        session.mount(scheme, adapter)
        logger.debug(f"Scheme '{scheme}' successfully mount to '{type(adapter).__name__}'")

    http_adapter = BearerAuthHTTPAdapter(oauth2_bearer) if oauth2_bearer else HTTPAdapter()
    _mount_session("http://", http_adapter)
    _mount_session("https://", http_adapter)
    _mount_session("file://", FileAdapter())

    authfile_path = Path(authfile) if authfile else None
    containers_auth = (
        ContainersAuth.get_instance(authfile_path)
        if authfile_path is not None and authfile_path.exists()
        else ContainersAuth(auths={})
    )

    if oci_hostname and oci_username and oci_password:
        containers_auth.add_auth(oci_hostname, oci_username, oci_password)
    _mount_session("oci://", OCIAdapter(containers_auth))

    start_time = time.time()
    exit_code = 0

    logger.info(
        f"Started at: {datetime.fromtimestamp(start_time).isoformat(timespec='milliseconds')}"
    )

    try:
        parsed_ogcrecords = _read_records(session, ogcrecords)

        reader = records_to_arrow(parsed_ogcrecords, batch_size=128)

        logger.info(f"Saving OGC Records to parquet format to {output.absolute()}...")
        output.parent.mkdir(parents=True, exist_ok=True)
        to_parquet(reader, output)

        logger.success("------------------------------------------------------------------------")
        logger.success("SUCCESS")
        logger.success(f"OGC Records successfully dumped to {output.absolute()} parquet file!")
        logger.success("------------------------------------------------------------------------")
    except Exception as error:
        exit_code = 1
        logger.error("------------------------------------------------------------------------")
        logger.error("FAIL")
        logger.exception(error)
        logger.error("------------------------------------------------------------------------")

    end_time = time.time()
    logger.info(f"Total time: {end_time - start_time:.4f} seconds")
    logger.info(
        f"Finished at: {datetime.fromtimestamp(end_time).isoformat(timespec='milliseconds')}"
    )

    if exit_code:
        sys.exit(exit_code)
