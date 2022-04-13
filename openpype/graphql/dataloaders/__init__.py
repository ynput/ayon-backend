"""
Dataloaders return a list of database rows, not the entities,
because they don't have access to the context object, which we
need for access control.
"""


from typing import Any, NewType

from openpype.exceptions import OpenPypeException
from openpype.lib.postgres import Postgres
from openpype.utils import SQLTool

KeyType = NewType("KeyType", tuple[str, str])
KeysType = NewType("KeysType", list[KeyType])


def get_project_name(keys: list[KeyType]) -> str:
    project_names = set(k[0] for k in keys)
    if len(project_names) != 1:
        raise OpenPypeException("Data loaders cannot perform cross-project requests")
    return project_names.pop()


async def folder_loader(keys: list[KeyType]) -> list[dict | None]:
    """Load a list of folders by their ids (used as a dataloader).
    keys must be a list of tuples (project_name, folder_id) and project_name
    values must be the same!
    """

    result_dict: dict[KeyType, Any] = {k: None for k in keys}
    project_name = get_project_name(keys)

    query = f"""
        SELECT
            folders.id AS id,
            folders.name AS name,
            folders.active AS active,
            folders.folder_type AS folder_type,
            folders.parent_id AS parent_id,
            folders.thumbnail_id AS thumbnail_id,
            folders.attrib AS attrib,
            folders.created_at AS created_at,
            folders.updated_at AS updated_at,
            hierarchy.path AS path
        FROM
            project_{project_name}.folders as folders

        LEFT JOIN
            project_{project_name}.hierarchy as hierarchy
            ON hierarchy.id = folders.id

        WHERE folders.id IN {SQLTool.id_array([k[1] for k in keys])}

        GROUP BY
            folders.id, hierarchy.path
    """

    async for record in Postgres.iterate(query):
        key: KeyType = KeyType((project_name, str(record["id"])))
        result_dict[key] = record
    return [result_dict[k] for k in keys]


async def folder_loader2(keys: list[KeyType]) -> list[dict | None]:
    """Load a list of folders by their ids (used as a dataloader).
    keys must be a list of tuples (project_name, folder_id) and project_name
    values must be the same!

    This is a more complex version which also returns subset_counts
    and children_counts.  which we probably do not need
    """

    result_dict = {k: None for k in keys}
    project_name = get_project_name(keys)

    query = f"""
        SELECT
            folders.id AS id,
            folders.name AS name,
            folders.active AS active,
            folders.folder_type AS folder_type,
            folders.parent_id AS parent_id,
            folders.attrib AS attrib,
            folders.created_at AS created_at,
            folders.updated_at AS updated_at,
            COUNT(children.id) AS children_count,
            COUNT(subsets.id) AS subset_count,
            hierarchy.path AS path
        FROM
            project_{project_name}.folders as folders

        LEFT JOIN
            project_{project_name}.hierarchy as hierarchy
            ON hierarchy.id = folders.id

        LEFT JOIN
            project_{project_name}.folders as children
            ON folders.id = children.parent_id

        LEFT JOIN
            project_{project_name}.subsets as subsets
            ON subsets.folder_id = folders.id

        WHERE folders.id IN {SQLTool.id_array([k[1] for k in keys])}

        GROUP BY
            folders.id, hierarchy.path
    """

    async for record in Postgres.iterate(query):
        key: KeyType = KeyType((project_name, str(record["id"])))
        result_dict[key] = record
    return [result_dict[k] for k in keys]


async def subset_loader(keys: list[KeyType]) -> list[dict | None]:
    """Load a list of subsets by their ids (used as a dataloader).
    keys must be a list of tuples (project_name, subset_id) and project_name
    values must be the same!
    """

    result_dict = {k: None for k in keys}
    project_name = get_project_name(keys)

    query = f"""
        SELECT * FROM project_{project_name}.subsets
        WHERE id IN {SQLTool.id_array([k[1] for k in keys])}
        """

    async for record in Postgres.iterate(query):
        key: KeyType = KeyType((project_name, str(record["id"])))
        result_dict[key] = record
    return [result_dict[k] for k in keys]


async def task_loader(keys: list[KeyType]) -> list[dict | None]:
    """Load a list of tasks by their ids (used as a dataloader).
    keys must be a list of tuples (project_name, task_id) and project_name
    values must be the same!
    """

    result_dict = {k: None for k in keys}
    project_name = get_project_name(keys)

    query = f"""
        SELECT * FROM project_{project_name}.tasks
        WHERE id IN {SQLTool.id_array([k[1] for k in keys])}
        """

    async for record in Postgres.iterate(query):
        key: KeyType = KeyType((project_name, str(record["id"])))
        result_dict[key] = record
    return [result_dict[k] for k in keys]


async def version_loader(keys: list[KeyType]) -> list[dict | None]:
    """Load a list of versions by their ids (used as a dataloader).
    keys must be a list of tuples (project_name, version_id) and project_name
    values must be the same!
    """

    result_dict = {k: None for k in keys}
    project_name = get_project_name(keys)

    query = f"""
        SELECT * FROM project_{project_name}.versions
        WHERE id IN {SQLTool.id_array([k[1] for k in keys])}
        """

    async for record in Postgres.iterate(query):
        key: KeyType = KeyType((project_name, str(record["id"])))
        result_dict[key] = record
    return [result_dict[k] for k in keys]


async def latest_version_loader(keys: list[KeyType]) -> list[dict | None]:
    """Load a list of latest versions of given subsets"""

    result_dict = {k: None for k in keys}
    project_name = get_project_name(keys)

    query = f"""
        SELECT
            v.id AS id,
            v.version AS version,
            v.subset_id AS subset_id,
            v.thumbnail_id AS thumbnail_id,
            v.task_id AS task_id,
            v.author AS author,
            v.attrib AS attrib,
            v.data AS data,
            v.active AS active,
            v.created_at AS created_at,
            v.updated_at AS updated_at
        FROM
            project_{project_name}.versions AS v
        WHERE v.id IN (
            SELECT l.ids[array_upper(l.ids, 1)]
            FROM project_{project_name}.version_list as l
            WHERE l.subset_id IN {SQLTool.id_array([k[1] for k in keys])}
        )
        """

    async for record in Postgres.iterate(query):
        key: KeyType = KeyType((project_name, str(record["subset_id"])))
        result_dict[key] = record
    return [result_dict[k] for k in keys]


async def user_loader(keys: list[str]) -> list[dict | None]:
    """Load a list of user records by their names."""

    result_dict = {k: None for k in keys}
    query = f"SELECT * FROM public.users WHERE id IN {SQLTool.id_array(keys)}"
    async for record in Postgres.iterate(query):
        result_dict[record["name"]] = record
    return [result_dict[k] for k in keys]
