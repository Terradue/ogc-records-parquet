# Your first round trip

In this tutorial you will create a record, write it to GeoParquet, recover it,
and export an edited JSON document. No external data service is needed.

## Prepare the environment

Use a local checkout and Python 3.11 or newer. From the repository root:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e .
```

On Windows, activate the environment with `.venv\Scripts\Activate.ps1`
in PowerShell instead.

Start Python from the repository root. Run the following Python blocks in
the same session.

## Create a record

```python
from pathlib import Path

from pystac.extensions.ogc_record import OGCRecord

from ogc_records_parquet import read_parquet, records_to_arrow, to_parquet

record = OGCRecord(
    id="flood-mapping",
    properties={
        "type": "service",
        "title": "Flood mapping",
        "keywords": ["flood", "mapping"],
    },
)
original = record.to_dict(transform_hrefs=False)
assert record.geometry is None
```

The record describes a service. It has no geometry or observation datetime;
neither is needed for this storage operation.

## Write the file

```python
output = Path("tutorial-output")
output.mkdir(exist_ok=True)
path = output / "records.parquet"

reader = records_to_arrow([record], batch_size=128)
to_parquet(reader, path)
assert path.is_file()
```

`reader` is a lazy Arrow stream. The writer consumes it and creates the file.
Running this step again replaces the destination after a successful write.

## Recover the record

```python
restored = list(read_parquet(path))
assert len(restored) == 1
assert isinstance(restored[0], OGCRecord)
assert restored[0].to_dict(transform_hrefs=False) == original
print(restored[0].title)
```

Expected output:

```text
Flood mapping
```

The equality compares PySTAC-serialized documents, not the bytes of an
original JSON file.

## Edit and export

```python
restored[0].title = "Updated flood mapping"
json_path = output / "updated-record.json"
restored[0].save_object(dest_href=str(json_path))
assert OGCRecord.from_file(json_path).title == "Updated flood mapping"
assert next(read_parquet(path)).title == "Flood mapping"
```

You now have a Parquet file and an edited JSON file under `tutorial-output/`.
Editing the recovered object does not modify the stored file.

Continue with [query projections](../how-to/project-filter.md) to select
records using Arrow columns, or read
[why the full document is stored](../explanation/preservation.md).
