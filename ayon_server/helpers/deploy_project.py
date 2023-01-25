from typing import Any

from ayon_server.entities import ProjectEntity, UserEntity
from ayon_server.lib.postgres import Postgres
from ayon_server.settings.anatomy import Anatomy


def anatomy_to_project_data(anatomy: Anatomy) -> dict[str, Any]:

    task_types = [t.dict() for t in anatomy.task_types]
    folder_types = [t.dict() for t in anatomy.folder_types]
    statuses = [t.dict() for t in anatomy.statuses]
    tags = [t.dict() for t in anatomy.tags]

    config: dict[str, Any] = {}
    config["roots"] = {}
    for root in anatomy.roots:
        config["roots"][root.name] = {
            "windows": root.windows,
            "linux": root.linux,
            "darwin": root.darwin,
        }

    config["templates"] = {
        "common": {
            "version_padding": anatomy.templates.version_padding,
            "version": anatomy.templates.version,
            "frame_padding": anatomy.templates.frame_padding,
            "frame": anatomy.templates.frame,
        }
    }
    for template_type in ("work", "publish", "hero", "delivery", "others"):
        template_group = anatomy.templates.dict().get(template_type, [])
        if not template_group:
            continue
        config["templates"][template_type] = {}
        for template in template_group:
            config["templates"][template_type][template["name"]] = {
                k: template[k] for k in template.keys() if k != "name"
            }

    return {
        "task_types": task_types,
        "folder_types": folder_types,
        "statuses": statuses,
        "tags": tags,
        "attrib": anatomy.attributes.dict(),  # type: ignore
        "config": config,
    }


async def create_project_from_anatomy(
    name: str,
    code: str,
    anatomy: Anatomy,
    library: bool = False,
) -> None:
    """Deploy a project.

    Create a new project with the given name and code, and deploy the
    given anatomy to it. Assing the project to all users with
    defaultRoles.

    This is a preffered way of creating a new project, as it will
    create all the necessary data in the database.
    """
    project = ProjectEntity(
        payload={
            "name": name,
            "code": code,
            "library": library,
            **anatomy_to_project_data(anatomy),
        },
    )

    async with Postgres.acquire() as conn:
        async with conn.transaction():

            await project.save(transaction=conn)

            # Assign the new project to all users with default roles

            # TBD: limit to active users only?
            # NOTE: we need to use explicit public here, because the
            # previous statement in the transaction scopes the transaction
            # to the project schema.
            query = """
                SELECT u.* FROM public.users AS u
                WHERE jsonb_array_length(data->'defaultRoles')::boolean
                FOR UPDATE OF u
            """

            users = await conn.fetch(query)

            for row in users:
                user = UserEntity.from_record(row)
                roles = user.data.get("roles", {})
                roles[project.name] = user.data["defaultRoles"]
                user.data["roles"] = roles
                await user.save(transaction=conn)
