"""
Dataloaders return a list of database rows, not the entities,
because they don't have access to the context object, which we
need for access control.
"""

from typing import Any, NewType

from ayon_server.exceptions import AyonException
from ayon_server.lib.postgres import Postgres

# from ayon_server.logging import logger
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

    # logger.trace(f"Using folder_loader for {len(keys)} keys")

    result_dict: dict[KeyType, Any] = dict.fromkeys(keys)
    project_name = get_project_name(keys)

    query = f"""
        SELECT
            folders.*,
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

    # logger.trace(f"Using product_loader for {len(keys)} keys")

    result_dict = dict.fromkeys(keys)
    project_name = get_project_name(keys)

    query = f"""
        SELECT
            products.*,
            hierarchy.path AS _folder_path
        FROM project_{project_name}.products AS products
        JOIN project_{project_name}.hierarchy AS hierarchy
        ON hierarchy.id = products.folder_id
        WHERE products.id IN {SQLTool.id_array([k[1] for k in keys])}
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

    # logger.trace(f"Using task_loader for {len(keys)} keys")

    result_dict = dict.fromkeys(keys)
    project_name = get_project_name(keys)

    query = f"""
        SELECT
            tasks.*,
            pf.attrib AS parent_folder_attrib,
            hierarchy.path AS _folder_path
        FROM project_{project_name}.tasks as tasks

        JOIN project_{project_name}.exported_attributes AS pf
        ON tasks.folder_id = pf.folder_id

        JOIN project_{project_name}.hierarchy AS hierarchy
        ON hierarchy.id = tasks.folder_id

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

    # logger.trace(f"Using workfile_loader for {len(keys)} keys")

    # TODO: query parent tasks?

    result_dict = dict.fromkeys(keys)
    project_name = get_project_name(keys)

    query = f"""
        SELECT
            workfiles.*,
            tasks.name AS _task_name,
            hierarchy.path AS _folder_path
        FROM
            project_{project_name}.workfiles
        JOIN project_{project_name}.tasks AS tasks
        ON tasks.id = workfiles.task_id

        JOIN project_{project_name}.hierarchy AS hierarchy
        ON hierarchy.id = tasks.folder_id

        WHERE workfiles.id IN {SQLTool.id_array([k[1] for k in keys])}
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

    # logger.trace(f"Using version_loader for {len(keys)} keys")

    result_dict = dict.fromkeys(keys)
    project_name = get_project_name(keys)

    query = f"""
        WITH reviewables AS (
            SELECT entity_id FROM project_{project_name}.activity_feed
            WHERE entity_type = 'version'
            AND activity_type = 'reviewable'
        ),

        hero_versions AS (
            SELECT version.id id, hero_version.id AS hero_version_id
            FROM project_{project_name}.versions AS version
            JOIN project_{project_name}.versions AS hero_version
            ON hero_version.product_id = version.product_id
            AND hero_version.version < 0
            AND ABS(hero_version.version) = version.version
        )

        SELECT
            versions.*,
            hero_versions.hero_version_id AS hero_version_id,
            hierarchy.path AS _folder_path,
            products.name AS _product_name,
            reviewables.entity_id IS NOT NULL AS has_reviewables
        FROM
            project_{project_name}.versions AS versions

        JOIN project_{project_name}.products AS products
        ON products.id = versions.product_id

        JOIN project_{project_name}.hierarchy AS hierarchy
        ON hierarchy.id = products.folder_id

        LEFT JOIN hero_versions
        ON hero_versions.id = versions.id

        LEFT JOIN reviewables
        ON reviewables.entity_id = versions.id

        WHERE versions.id IN {SQLTool.id_array([k[1] for k in keys])}
        """

    async for record in Postgres.iterate(query):
        key: KeyType = KeyType((project_name, str(record["id"])))
        result_dict[key] = record
    return [result_dict[k] for k in keys]


async def latest_version_loader(keys: list[KeyType]) -> list[dict[str, Any] | None]:
    """Load a list of latest versions of given products"""

    # logger.trace(f"Using latest_version_loader for {len(keys)} keys")

    result_dict = dict.fromkeys(keys)
    project_name = get_project_name(keys)

    query = f"""
        WITH reviewables AS (
            SELECT entity_id FROM project_{project_name}.activity_feed
            WHERE entity_type = 'version'
            AND activity_type = 'reviewable'
        ),

        hero_versions AS (
            SELECT version.id id, hero_version.id AS hero_version_id
            FROM project_{project_name}.versions AS version
            JOIN project_{project_name}.versions AS hero_version
            ON hero_version.product_id = version.product_id
            AND hero_version.version < 0
            AND ABS(hero_version.version) = version.version
        )

        SELECT
            v.*,
            hero_versions.hero_version_id AS hero_version_id,
            hierarchy.path AS _folder_path,
            p.name AS _product_name,
            EXISTS (
                SELECT 1 FROM reviewables WHERE entity_id = v.id
            ) AS has_reviewables
        FROM
            project_{project_name}.versions AS v

        JOIN project_{project_name}.products AS p
        ON p.id = v.product_id

        JOIN project_{project_name}.hierarchy AS hierarchy
        ON hierarchy.id = p.folder_id

        LEFT JOIN hero_versions
        ON hero_versions.id = v.id

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


async def representation_loader(keys: list[KeyType]) -> list[dict[str, Any] | None]:
    """Load a list of representations by their ids (used as a dataloader).
    keys must be a list of tuples (project_name, representation_id) and project_name
    values must be the same!
    """

    # logger.trace(f"Using representation_loader for {len(keys)} keys")

    result_dict = dict.fromkeys(keys)
    project_name = get_project_name(keys)

    query = f"""
        SELECT
            r.*,
            hierarchy.path AS _folder_path,
            p.name AS _product_name,
            v.version AS _version_number

        FROM
            project_{project_name}.representations AS r

        JOIN project_{project_name}.versions AS v
        ON v.id = r.version_id

        JOIN project_{project_name}.products AS p
        ON p.id = v.product_id

        JOIN project_{project_name}.hierarchy AS hierarchy
        ON hierarchy.id = p.folder_id

        WHERE r.id IN {SQLTool.id_array([k[1] for k in keys])}
        """

    async for record in Postgres.iterate(query):
        key: KeyType = KeyType((project_name, str(record["id"])))
        result_dict[key] = record
    return [result_dict[k] for k in keys]


async def user_loader(keys: list[str]) -> list[dict[str, Any] | None]:
    """Load a list of user records by their names."""

    # logger.trace(f"Using user_loader for {len(keys)} keys")

    result_dict = dict.fromkeys(keys)
    query = f"SELECT * FROM public.users WHERE name IN {SQLTool.array(keys)}"
    async for record in Postgres.iterate(query):
        result_dict[record["name"]] = record
    return [result_dict[k] for k in keys]
