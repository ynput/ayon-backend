import time

from ayon_server.cli import app
from ayon_server.exceptions import BadRequestException
from ayon_server.helpers.hierarchy_cache import rebuild_hierarchy_cache
from ayon_server.helpers.inherited_attributes import rebuild_inherited_attributes
from ayon_server.helpers.project_list import get_project_list
from ayon_server.initialize import ayon_init
from ayon_server.lib.postgres import Postgres
from ayon_server.logging import logger
from ayon_server.types import AttributeType


async def _do_migration(
    attrib_name: str, new_type: str, table_name: str, identifier: str
) -> None:
    if new_type == "string":
        replacement = """
            SELECT
                __IDENTIFIER__,
                CASE WHEN value IS NULL THEN NULL

                -- if value is already a string, keep it
                WHEN jsonb_typeof(value) = 'string'
                    THEN value

                -- if it was a list of strings, take the first element as the new value
                -- we don't care about the data loss here, since the user was warned
                WHEN jsonb_typeof(value) = 'array'
                    THEN value->0

                -- for other types, convert to string
                ELSE to_jsonb(value::text)
                END AS new_value
            FROM attr_values
        """

    elif new_type == "list_of_strings":
        replacement = """
            SELECT
                __IDENTIFIER__,
                CASE WHEN value IS NULL THEN NULL

                -- if value is already a list of strings, keep it
                WHEN jsonb_typeof(value) = 'array'
                    THEN value

                -- if it was a single string, convert to a list with one element
                WHEN jsonb_typeof(value) = 'string'
                    THEN to_jsonb(ARRAY[value #>> '{}'])

                -- for other types, convert to string and then to a list
                ELSE to_jsonb(ARRAY[value::text])

                END AS new_value
            FROM attr_values
        """

    else:
        raise BadRequestException(
            f"Changing data type to '{new_type}' is not supported. "
        )

    query = f"""
        WITH attr_values AS (
            SELECT __IDENTIFIER__, (attrib->$1) AS value
            FROM {table_name}
            WHERE attrib ? $1
        ),

        new_values AS (
            {replacement}
        )

        UPDATE {table_name} e
        SET attrib = COALESCE(
            jsonb_set(
                e.attrib,
                ARRAY[$1],
                n.new_value
            ),
            '{{}}'::jsonb
        )
        FROM new_values n
        WHERE e.__IDENTIFIER__ = n.__IDENTIFIER__
        AND e.attrib ? $1
    """

    query = query.replace("__IDENTIFIER__", identifier)
    await Postgres.execute(query, attrib_name)


@app.command()
async def migrate_attrib_type(
    attrib_name: str,
    new_type: AttributeType,
) -> None:
    await ayon_init()

    identifier = "id"

    start_time = time.perf_counter()

    projects = await get_project_list()
    for project in projects:
        for table_name in (
            "folders",
            "tasks",
            "products",
            "versions",
            "representations",
            "workfiles",
            "entity_lists",
        ):
            await _do_migration(
                attrib_name=attrib_name,
                new_type=new_type,
                table_name=f"project_{project.name}.{table_name}",
                identifier=identifier,
            )

    for project in projects:
        await rebuild_inherited_attributes(project.name)
        await rebuild_hierarchy_cache(project.name)

    identifier = "name"

    for table_name in ("projects", "users"):
        rmv = ""
        if new_type == "string":
            rm = ["min_items", "max_items", "gt", "lt", "ge", "le"]
            rmv = " - " + " - ".join(f"'{r}'" for r in rm)

        elif new_type == "list_of_strings":
            rm = ["min_length", "max_length", "gt", "lt", "ge", "le"]
            rmv = " - " + " - ".join(f"'{r}'" for r in rm)

        await Postgres.execute(
            f"UPDATE attributes SET data = (data || $1) {rmv} WHERE name = $2",
            {"type": new_type},
            attrib_name,
        )

    elapsed_time = time.perf_counter() - start_time

    logger.info(
        f"Migration of attribute '{attrib_name}' to type '{new_type}' "
        f"completed in {elapsed_time:.2f} seconds. Restart the server now!"
    )
