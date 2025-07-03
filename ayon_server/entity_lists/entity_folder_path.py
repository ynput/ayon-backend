from ayon_server.exceptions import NotFoundException
from ayon_server.lib.postgres import Postgres
from ayon_server.types import ProjectLevelEntityType


async def get_entity_folder_path(
    project_name: str,
    entity_type: ProjectLevelEntityType,
    entity_id: str,
) -> str:
    """Get the parent folder path of an entity

    We store the path in the list item record in order to solve
    access control.
    """

    async with Postgres.transaction():
        await Postgres.set_project_schema(project_name)
        joins = []

        if entity_type in ("product", "version", "representation"):
            joins.append(
                """
                INNER JOIN products
                ON products.folder_id = folders.id
                """
            )
            if entity_type in ("version", "representation"):
                joins.append(
                    """
                    INNER JOIN versions
                    ON versions.product_id = products.id
                    """
                )
                if entity_type == "representation":
                    joins.append(
                        """
                        INNER JOIN representations
                        ON representations.version_id = versions.id
                        """
                    )

        elif entity_type in ("task", "workfile"):
            joins.append(
                """
                INNER JOIN tasks
                ON tasks.folder_id = folders.id
                """
            )

            if entity_type == "workfile":
                joins.append(
                    """
                    INNER JOIN workfiles
                    ON workfiles.task_id = tasks.id
                    """
                )

        query = f"""
        SELECT folders.path as path
        FROM hierarchy as folders
        {' '.join(joins)}
        WHERE {entity_type}s.id = $1
        """
        res = await Postgres.fetchrow(query, entity_id)
        if not res:
            raise NotFoundException(f"{entity_type.capitalize()} {entity_id} not found")
        return res["path"]
