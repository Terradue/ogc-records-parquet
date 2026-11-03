# ogc-records-parquet

[![PyPI - Version](https://img.shields.io/pypi/v/ogc-records-parquet.svg)](https://pypi.org/project/ogc-records-parquet)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/ogc-records-parquet.svg)](https://pypi.org/project/ogc-records-parquet)
[![GitHub Actions Workflow Status](https://img.shields.io/github/actions/workflow/status/terradue/ogc-records-parquet/package.yaml?branch=develop&event=push&label=build&logo=githubactions)](https://github.com/terradue/ogc-records-parquet/actions/workflows/package.yaml?query=branch%3Adevelop)
[![Code coverage](https://img.shields.io/codecov/c/github/terradue/ogc-records-parquet/develop?logo=codecov)](https://app.codecov.io/gh/terradue/ogc-records-parquet/tree/develop)

Store `pystac.extensions.ogc_record.OGCRecord` objects in Arrow and GeoParquet.
The package preserves the extension's serialized document beside typed query
columns, with support for null geometry and explicit collection membership.

Requires Python 3.11 or newer. The test matrix covers Python 3.11–3.15.
Record parsing and serialization use
[`pystac-ext-ogc-record`](https://terradue.github.io/pystac-ext-ogc-record/).

## Quick start

Install from a local checkout:

```bash
python -m pip install -e .
```

```python
from pystac.extensions.ogc_record import OGCRecord

from ogc_records_parquet import read_parquet, records_to_arrow, to_parquet

record = OGCRecord(id="workflow", properties={"title": "Flood mapping"})
to_parquet(records_to_arrow([record]), "records.parquet")
restored = next(read_parquet("records.parquet"))
assert restored.to_dict() == record.to_dict()
```

Round trips preserve PySTAC-serialized values, not original JSON bytes.
OGC conformance and profile validation remain the caller's responsibility.

## Documentation

The [documentation](docs/index.md) follows [Diátaxis](https://diataxis.fr/):

- **Tutorials:** [your first round trip](docs/tutorials/first-round-trip.md).
- **How-to guides:** [import and export](docs/how-to/import-export.md),
  [project and filter](docs/how-to/project-filter.md),
  [collection membership](docs/how-to/collections.md), and
  [migration](docs/how-to/migrate.md).
- **Reference:** [Python API](docs/reference/api.md),
  [storage format](docs/reference/storage-format.md), and
  [errors and limitations](docs/reference/limitations.md).
- **Explanation:** [preservation and projections](docs/explanation/preservation.md)
  and [OGC Records and STAC](docs/explanation/ogc-and-stac.md).

Preview or build locally with Hatch:

```bash
hatch run docs:serve
hatch run docs:build
```

The strict build writes static HTML to `site/`. See
[development](docs/how-to/develop.md) for build options and authoring guidance.

## Development

```bash
hatch run dev:quality
hatch run test:test
hatch run docs:build
hatch build
```

The quality gate runs formatting, lint, typing, and security checks. Tests cover
round trips, projection safety, geometry, collection membership, and failure paths.

The [query notebook](notebooks/query_ogc_records.ipynb) demonstrates DuckDB and
CQL2 queries over the supplied examples. Install its dependencies with
`python -m pip install -e ".[notebook]"` and open it in a notebook-capable editor.

## License and acknowledgments

Licensed under [Apache-2.0](LICENSE). See [NOTICE](NOTICE) for upstream attribution
and [CHANGELOG.md](CHANGELOG.md) for the recorded project history.

[![Apache License, Version 2.0](https://img.shields.io/badge/license-Apache%20License%202.0-blue)](https://www.apache.org/licenses/LICENSE-2.0)

