# Import and export records

Use PySTAC for individual JSON documents. Install the package in your local
checkout before running these examples from the repository root.

For shell-based imports from local files or remote URLs, see the
[command-line interface](../reference/cli.md).

## Import an example file

```python
from pathlib import Path

from pystac.extensions.ogc_record import OGCRecord

from ogc_records_parquet import read_parquet, records_to_arrow, to_parquet

source = Path(
    "examples/ogc-records/hazard-mapping/records/diachronic-flood-detection.json"
)
record = OGCRecord.from_file(source)
to_parquet(records_to_arrow([record]), "imported.parquet")

restored = next(read_parquet("imported.parquet"))
assert restored.to_dict(transform_hrefs=False) == record.to_dict(transform_hrefs=False)
restored.save_object(dest_href="exported-record.json")
```

`from_file()` assigns a self link to the source file. Storage includes that
link and preserves relative hrefs without rewriting them.

## Read without adding a source self link

Use the following alternative when only links present in the document should
be retained:

```python
from pystac import StacIO
from pystac.extensions.ogc_record import OGCRecord

document = StacIO.default().read_json(
    "examples/ogc-records/hazard-mapping/records/diachronic-flood-detection.json"
)
record = OGCRecord.from_dict(document)
```

For in-memory dictionaries, likewise call `OGCRecord.from_dict(document)`
before `records_to_arrow()`. Select records from arrays or FeatureCollections
in the calling application. The package does not provide JSON container or
NDJSON readers.

## Edit links and assets

Use the record's PySTAC APIs before storing it again:

```python
from pystac import Asset, Link
from pystac.extensions.ogc_record import OGCRecord

from ogc_records_parquet import records_to_arrow, to_parquet

record = OGCRecord(id="workflow", properties={"title": "Flood workflow"})
record.add_link(Link("related", "../related.json"))
record.add_asset("workflow", Asset("./workflow.cwl", roles=["data"]))
to_parquet(records_to_arrow([record]), "workflow.parquet")
```

The asset href is stored as supplied; storage does not read or execute the
CWL document.

See [normalization and preservation](../explanation/preservation.md) for
timestamp and optional-field behavior.
