import copy
from typing import Any

from ayon_server.entities import UserEntity
from ayon_server.exceptions import (
    BadRequestException,
    ConflictException,
    NotFoundException,
)
from ayon_server.lib.postgres import Postgres
from ayon_server.utils import create_uuid, now

from .entity_list import EntityList
from .models import (
    EntityListItemModel,
    EntityListModel,
    EntityListSummary,
)

# data keys that grant access to the list for guests or make it public
PRIVATE_DATA_KEYS = ("publicLinks", "guestActivityCategories")
GUEST_ACCESS_KEY = "__guests__"
GUEST_ACCESS_PREFIX = "guest:"


def is_guest_access_key(key: str) -> bool:
    return key == GUEST_ACCESS_KEY or key.startswith(GUEST_ACCESS_PREFIX)


async def find_free_label(label: str) -> str:
    """Return the first of `label (copy)`, `label (copy 2)`... not in use"""

    base = f"{label} (copy"
    rows = await Postgres.fetch(
        "SELECT label FROM entity_lists WHERE starts_with(label, $1)", base
    )
    used = {row["label"] for row in rows}

    candidate = f"{base})"
    n = 1
    while candidate in used:
        n += 1
        candidate = f"{base} {n})"
    return candidate


async def duplicate_entity_list(
    project_name: str,
    source: EntityList,
    user: UserEntity,
    *,
    label: str | None = None,
    entity_list_folder_id: str | None = None,
    use_source_folder: bool = True,
) -> EntityListSummary:
    """Save a copy of the (fully loaded) source list owned by the user.

    The copy keeps everything but the ids, ownership, timestamps,
    guest access, public links and the active flag.
    Must be called within a transaction.
    """

    src = source.payload

    await Postgres.set_project_schema(project_name)

    if label is None:
        label = await find_free_label(src.label)
    else:
        label = label.strip()
        if not label:
            raise BadRequestException("Label cannot be empty")
        if await Postgres.fetchrow(
            "SELECT 1 FROM entity_lists WHERE label = $1", label
        ):
            raise ConflictException(f"Entity list '{label}' already exists")

    folder_id = (
        src.entity_list_folder_id if use_source_folder else entity_list_folder_id
    )
    if folder_id is not None and folder_id != src.entity_list_folder_id:
        if not await Postgres.fetchrow(
            "SELECT 1 FROM entity_list_folders WHERE id = $1", folder_id
        ):
            raise NotFoundException(f"Entity list folder {folder_id} not found")

    data: dict[str, Any] = copy.deepcopy(src.data)
    for key in PRIVATE_DATA_KEYS:
        data.pop(key, None)

    access = {k: v for k, v in src.access.items() if not is_guest_access_key(k)}

    timestamp = now()
    items = [
        EntityListItemModel(
            id=create_uuid(),
            entity_id=item.entity_id,
            position=position,
            label=item.label,
            attrib=copy.deepcopy(item.attrib),
            data=copy.deepcopy(item.data),
            tags=list(item.tags),
            folder_path=item.folder_path,
            created_by=user.name,
            updated_by=user.name,
            created_at=timestamp,
            updated_at=timestamp,
        )
        for position, item in enumerate(src.items)
    ]

    payload = EntityListModel(
        id=create_uuid(),
        entity_list_type=src.entity_list_type,
        entity_list_folder_id=folder_id,
        entity_type=src.entity_type,
        label=label,
        access=access,
        attrib=copy.deepcopy(src.attrib),
        data=data,
        template=copy.deepcopy(src.template),
        tags=list(src.tags),
        items=items,
        owner=user.name,
        created_by=user.name,
        updated_by=user.name,
        created_at=timestamp,
        updated_at=timestamp,
        active=True,
    )

    return await EntityList(project_name, payload, user=user).save()
