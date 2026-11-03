# Example collections

The eleven supplied Records are grouped into two example collections:

- `hazard-mapping`: four applications for burned-area, flood and volcanic plume mapping.
- `earth-observation-processing`: seven applications for processing, validation and ecosystem assessment.

Each collection directory contains `collection.json` metadata and a `records/` directory.
The Record documents are unchanged. Membership comes from the directory structure;
no STAC collection field or EOAP profile is added to the Records.

The query notebook loads `*/records/*.json` and stores both collection metadata
objects in its generated Parquet file. It supplies directory associations explicitly
as aligned `collection_ids`, storing them in `__collection_id` and verifying the
4/7 split from that column. Generic conversion code does not inspect directories.
