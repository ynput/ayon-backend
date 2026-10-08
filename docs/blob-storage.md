# Blob storage

`BlobStorage` lets addons store arbitrary binary payloads together with JSON metadata.
Blobs are scoped to a project and use the project storage (local or S3),
so addons don't need to handle persistence or storage configuration.

There are no REST endpoints for blobs. Addons expose their own endpoints if they need them.

```python
from ayon_server.blob_storage import BlobStorage

# Store a payload (bytes, an async iterator of bytes, or None)
blob_id = await BlobStorage.save(
    project_name,
    "io.ynput.my-addon.attachment",  # kind - categorizes the blob, e.g. the addon name
    payload,
    blob_id=blob_id,  # optional UUID, generated if omitted
    data={"source": "foo"},  # optional free-form metadata
)

record = await BlobStorage.get(project_name, blob_id)  # metadata only
payload = await BlobStorage.get_payload(project_name, blob_id)

async for chunk in BlobStorage.stream_payload(project_name, blob_id):
    ...

await BlobStorage.update(project_name, blob_id, {"status": "done"})
await BlobStorage.delete(project_name, blob_id)

# List records (metadata only), optionally by kind and metadata
async for record in BlobStorage.list(project_name, "io.ynput.my-addon.attachment", data={"status": "done"}):
    ...
```

## JSON records

The payload is optional. A blob saved without a payload (or with an empty one)
has size 0 and nothing in the project storage, so it can be used as a plain
JSON record stored in `data`. `get_payload` returns `b""` for such blobs.

To look records up by a readable key, derive the blob id from it:

```python
import uuid

blob_id = uuid.uuid5(MY_NAMESPACE, f"my-addon").hex
await BlobStorage.save(project_name, "io.ynput.ayon.addon-config", blob_id=blob_id, data={...})
```

## Behavior

- `kind` is 1-64 characters (letters, digits, `_`, `.`, `-`), not starting or ending with `.` or `-`.
- `blob_id` is a UUID (32 hex characters, dashes are allowed). It is generated when omitted.
  Invalid ids raise `ValueError`.
- The blob id alone identifies a blob within a project.
- Saving with an existing id of the same kind overwrites the payload, metadata and size.
  `created_at` / `created_by` stay unchanged.
- Saving with an id that belongs to another kind raises `ConflictException`.
- `list` returns the records oldest first. The `data` filter matches blobs
  whose metadata contains all the given key-value pairs.
- `update` shallow-merges the provided keys into the existing metadata.
  The payload is not touched.
- `created_by` / `updated_by` are taken from the request context.
- Reading, updating or deleting a non-existent blob raises `NotFoundException`.
- If the payload cannot be stored, no record is created.
  If the record of a new blob cannot be created, the stored payload is removed.

## Storage layout

Metadata is stored in the `blobs` table of the project schema.
Payloads are stored in the project storage under `blobs/{kind}/{blob_id[:2]}/{blob_id}`.
Blobs of size 0 have no payload in the storage.
Blobs are removed with the rest of the project when the project is deleted.
