"""Entity parents resolver

Resolves activity.data.parents from entity.
`parents` field is a list of dictionaries describing parent entities.
It's structured as follows:

[
    {
        "type": "folder",
        "subtype": "Asset",
        "id": "folder_id",
        "name": "cthulhu",
        "label": "Cthulhu",
    },
    {
        "type": "task",
        "subtype": "Modeling",
        "id": "task_id",
        "name": "modeling",
    },
]

Supported types are `task`, `product`
Depending on the type, subtype is either taskType or productType.
label may not be present (or set to null), when no explicit label is set on the entity.

Version: [folder, product]
Task: [folder]

We don't show full hierarchy, so we don't need to resolve parents for folders.
"""

__all__ = ["get_parents_from_entity"]

from ayon_server.entities import TaskEntity, VersionEntity
from ayon_server.entities.core import ProjectLevelEntity
from ayon_server.lib.postgres import Postgres


async def get_parents_from_task(task: TaskEntity) -> list[dict[str, str]]:
    query = f"""
        SELECT id, name, label, folder_type as subtype
        FROM project_{task.project_name}.folders WHERE id = $1
    """

    res = await Postgres.fetch(query, task.folder_id)
    assert res, "This shouldn't happen"
    row = res[0]
    return [
        {
            "type": "folder",
            "subtype": row["subtype"],
            "id": row["id"],
            "name": row["name"],
            "label": row["label"],
        }
    ]


async def get_parents_from_version(version: VersionEntity) -> list[dict[str, str]]:
    query = f"""
        SELECT
            p.id as product_id,
            p.name as product_name,
            p.product_type as product_type,
            f.id as folder_id,
            f.name as folder_name,
            f.folder_type as folder_type,
            f.label as folder_label
        FROM project_{version.project_name}.products p
        JOIN project_{version.project_name}.folders f ON p.folder_id = f.id
        WHERE p.id = $1
    """

    res = await Postgres.fetch(query, version.product_id)
    assert res, "This shouldn't happen"
    row = res[0]
    return [
        {
            "type": "folder",
            "subtype": row["folder_type"],
            "id": row["folder_id"],
            "name": row["folder_name"],
            "label": row["folder_label"],
        },
        {
            "type": "product",
            "subtype": row["product_type"],
            "id": row["product_id"],
            "name": row["product_name"],
        },
    ]


async def get_parents_from_entity(
    entity: ProjectLevelEntity,
) -> list[dict[str, str]]:
    if isinstance(entity, TaskEntity):
        return await get_parents_from_task(entity)
    elif isinstance(entity, VersionEntity):
        return await get_parents_from_version(entity)
    else:
        return []
