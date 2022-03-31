from nxtools import logging

from openpype.lib.postgres import Postgres
from openpype.entities.common import Entity
from openpype.entities import FolderEntity, SubsetEntity, VersionEntity
from openpype.utils import EntityID


def entity_from_record(entity_type, project_name, record):
    return {"folder": FolderEntity, "subset": SubsetEntity, "version": VersionEntity}[
        entity_type
    ].from_record(project_name, **record)


async def create_link(
    input_entity: Entity, output_entity: Entity, link_type: str, **kwargs
) -> str:
    assert input_entity.project_name == output_entity.project_name
    project_name = input_entity.project_name

    link_id = EntityID.create()
    link_type_name = (
        f"{link_type}|{input_entity.entity_name}|{output_entity.entity_name}"
    )

    logging.info(
        f"Creating {link_type} link between {input_entity} and {output_entity}"
    )
    await Postgres.execute(
        f"""
        INSERT INTO project_{project_name}.links
            (id, input_id, output_id, link_name, data)
        VALUES
            ($1, $2, $3, $4, $5)
        """,
        link_id,
        input_entity.id,
        output_entity.id,
        link_type_name,
        kwargs,
    )


async def make_links(
    project_name: str,
    link_type: str,
    input_type: str,
    output_type: str,
) -> None:
    logging.info(f"Creating links in project {project_name}")

    in_query = f"SELECT * FROM project_{project_name}.{input_type}s"
    out_query = f"""
        SELECT * FROM project_{project_name}.{output_type}s
        ORDER BY RANDOM() LIMIT 10
    """
    async for row in Postgres.iterate(in_query):
        input_entity = entity_from_record(input_type, project_name, row)

        async for outrow in Postgres.iterate(out_query):
            output_entity = entity_from_record(output_type, project_name, outrow)
            await create_link(input_entity, output_entity, link_type, author="martas")
