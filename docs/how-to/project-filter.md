# Project and filter records

Supply an Arrow schema when you need query columns beyond the defaults.
Use dot-separated object paths as field names.

## Select the columns

This complete example builds two records and projects their service type,
title, and update time:

```python
import pyarrow as pa
import pyarrow.compute as pc
from pystac.extensions.ogc_record import OGCRecord

from ogc_records_parquet import arrow_to_records, records_to_arrow

records = [
    OGCRecord(
        id="flood",
        properties={
            "type": "service",
            "title": "Flood mapping",
            "updated": "2026-01-01T00:00:00Z",
        },
    ),
    OGCRecord(id="archive", properties={"type": "dataset", "title": "Archive"}),
]
schema = pa.schema([
    pa.field("id", pa.string(), nullable=False),
    pa.field("properties.type", pa.string()),
    pa.field("properties.title", pa.string()),
    pa.field("properties.updated", pa.timestamp("us", tz="UTC")),
])
table = records_to_arrow(records, schema=schema, batch_size=1).read_all()
assert table["properties.updated"].null_count == 1

selected = table.filter(pc.equal(table["properties.type"], "service"))
restored = list(arrow_to_records(selected))
assert [record.id for record in restored] == ["flood"]
assert restored[0].to_dict() == records[0].to_dict()
```

Keep `__record_json` and the format metadata when passing results back to
`arrow_to_records()`. Filtering full rows retains these. Selecting only query
columns prevents record reconstruction.

## Project nested lists

An explicit list/struct type can project a whole list:

```python
schema = pa.schema([
    pa.field("id", pa.string()),
    pa.field("links", pa.list_(pa.struct([
        pa.field("href", pa.string()),
        pa.field("rel", pa.string()),
        pa.field("type", pa.string()),
    ]))),
])
table = records_to_arrow(records, schema=schema).read_all()
assert table.num_rows == 2
```

Paths do not traverse list elements or escape literal dots in object keys.
Handle those cases in the calling application. Missing paths project as null;
use `nullable=False` to reject them. Unsafe numeric casts fail when the stream
is consumed.

## Query with SQL

Dotted names are literal column names. In DuckDB, quote them:

```sql
SELECT id, "properties.title"
FROM read_parquet('records.parquet')
WHERE "properties.type" = 'service';
```

SQL execution is outside this package. The repository notebook at
`notebooks/query_ogc_records.ipynb` demonstrates collection filtering and CQL2
translation with `pygeofilter-duckdb==0.2.0`.

Install its dependencies from the checkout:

```bash
python -m pip install -e ".[notebook]"
```

Open the notebook in a notebook-capable editor using that Python environment.
It writes `notebooks/output/ogc-records.parquet`. See the
[storage reference](../reference/storage-format.md) for the reserved columns.
