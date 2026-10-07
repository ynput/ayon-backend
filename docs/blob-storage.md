# Blob storage

`BlobStorage` lets addons store arbitrary binary payloads together with JSON metadata.
Blobs are scoped to a project and use the project storage (local or S3),
so addons don't need to handle persistence or storage configuration.

There are no REST endpoints for blobs. Addons expose their own endpoints if they need them.

```python
from ayon_server.blob_storage import BlobStorage

# Store a payload (bytes or an async iterator of bytes)
blob_id = await BlobStorage.save(
    project_name,
    "my_addon",  # kind - categorizes the blob, e.g. the addon name
    payload,
    blob_id="cache-v1",  # optional, generated if omitted
    data={"source": "foo"},  # optional free-form metadata
)

record = await BlobStorage.get(project_name, blob_id)  # metadata only
payload = await BlobStorage.get_payload(project_name, blob_id)

async for chunk in BlobStorage.stream_payload(project_name, blob_id):
    ...

await BlobStorage.update(project_name, blob_id, {"status": "done"})
await BlobStorage.delete(project_name, blob_id)
```

## Behavior

- `kind` and `blob_id` must match `NAME_REGEX` (letters, digits, `_`, `.`, `-`).
- The blob id alone identifies a blob within a project.
- Saving with an existing id of the same kind overwrites the payload, metadata and size.
  `created_at` / `created_by` stay unchanged.
- Saving with an id that belongs to another kind raises `ConflictException`.
- `update` shallow-merges the provided keys into the existing metadata.
  The payload is not touched.
- `created_by` / `updated_by` are taken from the request context.
- Reading, updating or deleting a non-existent blob raises `NotFoundException`.
- If the payload cannot be stored, no record is created.
  If the record of a new blob cannot be created, the stored payload is removed.

## Storage layout

Metadata is stored in the `blobs` table of the project schema.
Payloads are stored in the project storage under `blobs/{kind}/{blob_id}`.
Blobs are removed with the rest of the project when the project is deleted.
