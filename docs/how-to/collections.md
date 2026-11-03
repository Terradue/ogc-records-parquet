# Store collection membership

Supply catalog descriptions and per-row memberships separately. Descriptions
alone do not establish membership.

```python
from pystac.extensions.ogc_record import OGCRecord

from ogc_records_parquet import (
    read_collection_ids,
    read_collections,
    read_parquet,
    records_to_arrow,
    to_parquet,
)

records = [
    OGCRecord(id="shared-id", properties={"title": "Application"}),
    OGCRecord(id="shared-id", properties={"title": "Unclassified"}),
]
catalogs = {
    "applications": {
        "id": "applications",
        "type": "Collection",
        "links": [],
        "itemType": "record",
    },
}
memberships = ["applications", None]
to_parquet(
    records_to_arrow(records, collections=catalogs, collection_ids=memberships),
    "collections.parquet",
)

assert read_collections("collections.parquet") == catalogs
assert list(read_collection_ids("collections.parquet")) == memberships
assert [record.id for record in read_parquet("collections.parquet")] == [
    "shared-id", "shared-id"
]
```

## Align membership with rows

- Provide exactly one membership per record, in the same order.
- Use a non-empty string for known membership and `None` for unknown membership.
- Keep both iterables aligned when generating them lazily.
- Pair separately read records and memberships only when they represent the
  same rows in the same order.

Length mismatches and invalid membership values fail during consumption.
Duplicate record identifiers are allowed because association is positional.

## Preserve the original record

`__collection_id` is storage-only membership. It does not replace or insert
the record's `collection` field. Catalog descriptions are serialized into
metadata during `records_to_arrow()`; later changes to the supplied dictionaries
do not change that snapshot.

The library requires catalog values to be JSON objects. It does not validate
catalog schemas, match their IDs to mapping keys, or require membership IDs to
have descriptions.

For older files, see [migration](migrate.md).
