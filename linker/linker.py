from typing import Any

from nxtools import logging

from ayon_server.lib.postgres import Postgres
from ayon_server.utils import EntityID
from linker.query import query_entities

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
            f"{input_type} {input_id} and "
            f"{output_type} {output_id}"
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
    async for input_entity in query_entities(
        project_name,
        input_type,
        **link_type_config["input"],
    ):
        out_config: dict[str, Any] = link_type_config["output"]
        if link_type_config.get("same_folder", False):
            out_config["folder_id"] = input_entity.folder_id
        if link_type_config.get("link_matching_versions", False):
            out_config["version"] = input_entity.version

        async for output_entity in query_entities(
            project_name, output_type, **out_config
        ):
            await create_link(
                project_name,
                input_entity.id,
                output_entity.id,
                link_type_name,
                author="martas",
            )
            count += 1
    logging.goodnews(
        f"Created {count} {link_type_name} links for project {project_name}"
    )
