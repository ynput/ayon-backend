from typing import Any, AsyncGenerator, Literal

from nxtools import logging

from openpype.lib.postgres import Postgres
from openpype.utils import EntityID, SQLTool

DEBUG = False


async def create_link(
    project_name: str,
    input_id: str,
    output_id: str,
    link_type_name: str,
    **kwargs,
) -> None:

    link_type, input_type, output_type = link_type_name.split("|")
    link_id = EntityID.create()

    if DEBUG:
        logging.debug(
            f"Creating {link_type} link between "
            f" {input_type} {input_id} and "
            f" {output_type} {output_id}"
        )
    await Postgres.execute(
        f"""
        INSERT INTO project_{project_name}.links
            (id, input_id, output_id, link_name, data)
        VALUES
            ($1, $2, $3, $4, $5)
        """,
        link_id,
        input_id,
        output_id,
        link_type_name,
        kwargs,
    )


async def query_entities(
    project_name: str,
    entity_type: str,
    folder_path: str | None = None,
    folder_type: str | None = None,
    folder_id: str | None = None,
    subset_name: str | None = None,
    limit: int | None = None,
    version: Literal["same", "latest"] | None = None,
) -> AsyncGenerator[tuple[str, str], None]:
    """Query entities from a project.

    Returns a generator of tuples of (folder_id, entity_id) for a
    given entity type and filters.
    """

    conditions = []

    if folder_id is not None:
        conditions.append(f"folder_id = '{folder_id}'")
    if folder_type is not None:
        conditions.append(f"folder_type = '{folder_type}'")
    if folder_path is not None:
        conditions.append(f"h.path ~* '{folder_path}'")
    if subset_name is not None:
        conditions.append(f"s.name ~* '{subset_name}'")

    if limit is not None:
        cols = ["f.id as folder_id", "s.id as subset_id", "v.id as version_id"]
    else:
        if entity_type == "folder":
            cols = [
                "distinct(f.id) as folder_id",
                "s.id as subset_id",
                "v.id as version_id",
            ]
        elif entity_type == "subset":
            cols = [
                "distinct(s.id) as subset_id",
                "f.id as folder_id",
                "v.id as version_id",
            ]
        elif entity_type == "version":
            cols = [
                "distinct(v.id) as version_id",
                "f.id as folder_id",
                "s.id as subset_id",
            ]
        else:
            raise ValueError(f"Unknown entity type: {entity_type}")

    cols.append("h.path as path")
    cols.append("s.name as subset_name")
    cols.append("s.family as subset_family")

    query = f"""
        SELECT {", ".join(cols)}
        FROM
            project_{project_name}.folders f
        INNER JOIN
            project_{project_name}.subsets s
            ON f.id = s.folder_id
        INNER JOIN
            project_{project_name}.versions v
            ON s.id = v.subset_id
        LEFT JOIN
            project_{project_name}.hierarchy h
            ON f.id = h.id
        {SQLTool.conditions(conditions)}
        {'ORDER BY RANDOM()' if limit is not None else ''}
    """
    used: list[str] = []  # faster that trying to find out, how to distinct
    async for row in Postgres.iterate(query):
        if row[f"{entity_type}_id"] in used:
            continue
        used.append(row[f"{entity_type}_id"])
        # print("returning", entity_type, row["path"], row["subset_name"])
        yield row["folder_id"], row[f"{entity_type}_id"]
        if limit is not None and len(used) >= limit:
            break


async def make_links(
    project_name: str,
    link_type_config: dict[str, Any],
) -> None:
    logging.info(f"Creating links in project {project_name}")
    link_type_name = link_type_config["link_type"]
    link_type, input_type, output_type = link_type_name.split("|")

    if "input" not in link_type_config:
        raise ValueError(f"Missing input config in link type {link_type_name}")
    if "output" not in link_type_config:
        raise ValueError(f"Missing output config in link type {link_type_name}")

    count = 0
    async for folder_id, input_id in query_entities(
        project_name,
        input_type,
        **link_type_config["input"],
    ):
        lconfig = {}
        if link_type_config.get("same_folder", False):
            lconfig["folder_id"] = folder_id

        async for _, output_id in query_entities(
            project_name,
            output_type,
            **link_type_config["output"] | lconfig,
        ):

            await create_link(
                project_name,
                input_id,
                output_id,
                link_type_name,
                author="martas",
            )
            count += 1
    logging.goodnews(
        f"Created {count} {link_type_name} links for project {project_name}"
    )
