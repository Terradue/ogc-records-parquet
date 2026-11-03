# Command-line interface

Install the optional CLI dependencies:

```sh
pip install 'ogc-records-parquet[cli]'
ogc-records-parquet --help
```

## Import records

Pass one or more individual OGC Record JSON documents and a destination:

```sh
ogc-records-parquet \
  examples/ogc-records/hazard-mapping/records/diachronic-flood-detection.json \
  --output output/records.parquet
```

Inputs may mix local paths with HTTP, HTTPS, `file://`, and `oci://` URLs.
Records retain their argument order. Each source must contain one record;
arrays, FeatureCollections, and NDJSON are not supported. The CLI parses sources
with PySTAC's `OGCRecord.from_dict()`, without adding a source self link.

The command loads all records before writing, creates missing output directories,
and overwrites an existing destination. It does not provide streaming ingestion,
filtering, or JSON export. Use the [Python API](api.md) for those workflows.

## Options and authentication

| Option | Environment variable | Behavior |
| --- | --- | --- |
| `--output PATH` | — | Required destination GeoParquet file. |
| `--oauth2-bearer TOKEN` | `OAUTH2_BEARER` | Bearer token for HTTP and HTTPS requests. |
| `--oci-hostname HOST` | `OCI_HOSTNAME` | Registry host for explicit credentials. |
| `--oci-username USER` | `OCI_USERNAME` | Registry username. |
| `--oci-password PASSWORD` | `OCI_PASSWORD` | Registry password. |
| `--authfile PATH` | `REGISTRY_AUTH_FILE` | Registry credentials file. |
| `--help` | — | Show usage and exit. |

Explicit options take precedence over their environment variables. All three OCI
credential options must be supplied to add credentials for the specified host.
A credentials file can also supply registry authentication. If it does not exist,
the command starts with empty credentials before adding explicit credentials.

The default credentials path is resolved when the command runs:

- Linux with a nonempty `XDG_RUNTIME_DIR`: `$XDG_RUNTIME_DIR/containers/auth.json`.
- Otherwise, including macOS and Windows: `~/.config/containers/auth.json`.

For authenticated HTTP sources, set `OAUTH2_BEARER` in the invoking environment:

```sh
ogc-records-parquet https://catalog.example.org/records/workflow.json \
  --output records.parquet
```

## Exit status

- `0`: conversion succeeded, or help was displayed.
- `1`: a source could not be read or parsed, or output could not be written.
- `2`: invalid command usage, such as missing inputs or `--output`.

Progress and diagnostic logs are written to standard error. A failed write may
leave a partial output file; output replacement is not atomic.
