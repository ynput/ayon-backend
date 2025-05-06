"""
Dataloaders return a list of database rows, not the entities,
because they don't have access to the context object, which we
need for access control.
"""

from typing import Any, NewType

from ayon_server.exceptions import AyonException
from ayon_server.lib.postgres import Postgres
from ayon_server.utils import SQLTool

KeyType = NewType("KeyType", tuple[str, str])
KeysType = NewType("KeysType", list[KeyType])


def get_project_name(keys: list[KeyType]) -> str:
    project_names = {k[0] for k in keys}
    if len(project_names) != 1:
        raise AyonException("Data loaders cannot perform cross-project requests")
    return project_names.pop()


async def folder_loader(keys: list[KeyType]) -> list[dict[str, Any] | None]:
    """Load a list of folders by their ids (used as a dataloader).
    keys must be a list of tuples (project_name, folder_id) and project_name
    values must be the same!
    """

    result_dict: dict[KeyType, Any] = dict.fromkeys(keys)
    project_name = get_project_name(keys)

    query = f"""
        SELECT
            folders.id AS id,
            folders.name AS name,
            folders.label AS label,
            folders.active AS active,
            folders.folder_type AS folder_type,
            folders.parent_id AS parent_id,
            folders.thumbnail_id AS thumbnail_id,
            folders.attrib AS attrib,
            folders.status AS status,
            folders.tags AS tags,
            folders.created_at AS created_at,
            folders.updated_at AS updated_at,
            folders.data as data,
            hierarchy.path AS path,
            pr.attrib AS project_attributes,
            ex.attrib AS inherited_attributes
        FROM
            project_{project_name}.folders as folders

        LEFT JOIN
            project_{project_name}.hierarchy as hierarchy
            ON hierarchy.id = folders.id
        LEFT JOIN
            project_{project_name}.exported_attributes AS ex
            ON folders.parent_id = ex.folder_id
        INNER JOIN
            public.projects AS pr
            ON pr.name ILIKE '{project_name}'

        WHERE folders.id IN {SQLTool.id_array([k[1] for k in keys])}

        GROUP BY
            folders.id, hierarchy.path, pr.attrib, ex.attrib
    """

    async for record in Postgres.iterate(query):
        key: KeyType = KeyType((project_name, str(record["id"])))
        result_dict[key] = record
    return [result_dict[k] for k in keys]


async def product_loader(keys: list[KeyType]) -> list[dict[str, Any] | None]:
    """Load a list of products by their ids (used as a dataloader).
    keys must be a list of tuples (project_name, product_id) and project_name
    values must be the same!
    """

    result_dict = dict.fromkeys(keys)
    project_name = get_project_name(keys)

    query = f"""
        SELECT * FROM project_{project_name}.products
        WHERE id IN {SQLTool.id_array([k[1] for k in keys])}
        """

    async for record in Postgres.iterate(query):
        key: KeyType = KeyType((project_name, str(record["id"])))
        result_dict[key] = record
    return [result_dict[k] for k in keys]


async def task_loader(keys: list[KeyType]) -> list[dict[str, Any] | None]:
    """Load a list of tasks by their ids (used as a dataloader).
    keys must be a list of tuples (project_name, task_id) and project_name
    values must be the same!
    """

    result_dict = dict.fromkeys(keys)
    project_name = get_project_name(keys)

    query = f"""
        SELECT
            tasks.id AS id,
            tasks.name AS name,
            tasks.label AS label,
            tasks.folder_id AS folder_id,
            tasks.task_type AS task_type,
            tasks.thumbnail_id AS thumbnail_id,
            tasks.assignees AS assignees,
            tasks.attrib AS attrib,
            tasks.data AS data,
            tasks.active AS active,
            tasks.status AS status,
            tasks.tags AS tags,
            tasks.created_at AS created_at,
            tasks.updated_at AS updated_at,
            tasks.creation_order AS creation_order,
            pf.attrib AS parent_folder_attrib
        FROM project_{project_name}.tasks
        LEFT JOIN project_{project_name}.exported_attributes AS pf
        ON tasks.folder_id = pf.folder_id

        WHERE tasks.id IN {SQLTool.id_array([k[1] for k in keys])}
        """

    async for record in Postgres.iterate(query):
        key: KeyType = KeyType((project_name, str(record["id"])))
        result_dict[key] = record
    return [result_dict[k] for k in keys]


async def workfile_loader(keys: list[KeyType]) -> list[dict[str, Any] | None]:
    """Load a list of workfiles by their ids (used as a dataloader).
    keys must be a list of tuples (project_name, workfile_id) and project_name
    values must be the same!
    """

    # TODO: query parent tasks?

    result_dict = dict.fromkeys(keys)
    project_name = get_project_name(keys)

    query = f"""
        SELECT * FROM project_{project_name}.workfiles
        WHERE id IN {SQLTool.id_array([k[1] for k in keys])}
        """

    async for record in Postgres.iterate(query):
        key: KeyType = KeyType((project_name, str(record["id"])))
        result_dict[key] = record
    return [result_dict[k] for k in keys]


async def version_loader(keys: list[KeyType]) -> list[dict[str, Any] | None]:
    """Load a list of versions by their ids (used as a dataloader).
    keys must be a list of tuples (project_name, version_id) and project_name
    values must be the same!
    """

    result_dict = dict.fromkeys(keys)
    project_name = get_project_name(keys)

    query = f"""
        WITH reviewables AS (
            SELECT entity_id FROM project_{project_name}.activity_feed
            WHERE entity_type = 'version'
            AND activity_type = 'reviewable'
        )

        SELECT
            v.id AS id,
            v.version AS version,
            v.product_id AS product_id,
            v.thumbnail_id AS thumbnail_id,
            v.task_id AS task_id,
            v.author AS author,
            v.attrib AS attrib,
            v.data AS data,
            v.active AS active,
            v.status AS status,
            v.tags AS tags,
            v.created_at AS created_at,
            v.updated_at AS updated_at,
            EXISTS (
                SELECT 1 FROM reviewables WHERE entity_id = v.id
            ) AS has_reviewables
        FROM project_{project_name}.versions AS v
        WHERE v.id IN {SQLTool.id_array([k[1] for k in keys])}
        """

    async for record in Postgres.iterate(query):
        key: KeyType = KeyType((project_name, str(record["id"])))
        result_dict[key] = record
    return [result_dict[k] for k in keys]


async def latest_version_loader(keys: list[KeyType]) -> list[dict[str, Any] | None]:
    """Load a list of latest versions of given products"""

    result_dict = dict.fromkeys(keys)
    project_name = get_project_name(keys)

    query = f"""
        WITH reviewables AS (
            SELECT entity_id FROM project_{project_name}.activity_feed
            WHERE entity_type = 'version'
            AND activity_type = 'reviewable'
        )

        SELECT
            v.id AS id,
            v.version AS version,
            v.product_id AS product_id,
            v.thumbnail_id AS thumbnail_id,
            v.task_id AS task_id,
            v.author AS author,
            v.attrib AS attrib,
            v.data AS data,
            v.active AS active,
            v.status AS status,
            v.tags AS tags,
            v.created_at AS created_at,
            v.updated_at AS updated_at,
            EXISTS (
                SELECT 1 FROM reviewables WHERE entity_id = v.id
            ) AS has_reviewables
        FROM
            project_{project_name}.versions AS v
        WHERE v.id IN (
            SELECT l.ids[array_upper(l.ids, 1)]
            FROM project_{project_name}.version_list as l
            WHERE l.product_id IN {SQLTool.id_array([k[1] for k in keys])}
        )
        """

    async for record in Postgres.iterate(query):
        key: KeyType = KeyType((project_name, str(record["product_id"])))
        result_dict[key] = record
    return [result_dict[k] for k in keys]


async def user_loader(keys: list[str]) -> list[dict[str, Any] | None]:
    """Load a list of user records by their names."""

    result_dict = dict.fromkeys(keys)
    query = f"SELECT * FROM public.users WHERE name IN {SQLTool.array(keys)}"
    async for record in Postgres.iterate(query):
        result_dict[record["name"]] = record
    return [result_dict[k] for k in keys]
