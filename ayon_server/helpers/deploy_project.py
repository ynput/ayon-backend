import time
from typing import Any

from nxtools import logging

from ayon_server.auth.session import Session
from ayon_server.entities import ProjectEntity, UserEntity
from ayon_server.entities.models.submodels import LinkTypeModel
from ayon_server.events import dispatch_event
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
    for template_type in (
        "work",
        "publish",
        "hero",
        "delivery",
        "others",
        "staging_directories",
    ):
        template_group = anatomy.templates.dict().get(template_type, [])
        if not template_group:
            continue
        config["templates"][template_type] = {}
        for template in template_group:
            config["templates"][template_type][template["name"]] = {
                k: template[k] for k in template.keys() if k != "name"
            }

    link_types: list[LinkTypeModel] = []
    for link_type in anatomy.link_types:
        name = f"{link_type.link_type}|{link_type.input_type}|{link_type.output_type}"
        data = {"color": link_type.color, "style": link_type.style}
        link_types.append(
            LinkTypeModel(
                name=name,
                link_type=link_type.link_type,
                input_type=link_type.input_type,
                output_type=link_type.output_type,
                data=data,
            )
        )

    result = {
        "task_types": task_types,
        "folder_types": folder_types,
        "link_types": link_types,
        "statuses": statuses,
        "tags": tags,
        "attrib": anatomy.attributes.dict(),
        "config": config,
    }

    return result


async def assign_default_users_to_project(project_name: str, conn) -> None:
    """Assign a project to all users with default access groups"""

    # TBD: limit to active users only?
    # NOTE: we need to use explicit public here, because the
    # previous statement in the transaction scopes the transaction
    # to the project schema.
    query = """
        SELECT u.* FROM public.users AS u
        WHERE jsonb_array_length(data->'defaultAccessGroups')::boolean
        FOR UPDATE OF u
    """

    users = await conn.fetch(query)

    for row in users:
        logging.debug(f"Assigning project {project_name} to user {row['name']}")
        user = UserEntity.from_record(row)

        if user.is_manager:
            # we don't need to assign projects to managers and above
            # as they have access to all projects
            continue

        access_groups = user.data.get("accessGroups", {})
        access_groups[project_name] = user.data["defaultAccessGroups"]
        user.data["accessGroups"] = access_groups
        await user.save(transaction=conn)

        async for session in Session.list(user.name):
            token = session.token
            await Session.update(token, user)


async def create_project_from_anatomy(
    name: str,
    code: str,
    anatomy: Anatomy,
    library: bool = False,
) -> None:
    """Deploy a project.

    Create a new project with the given name and code, and deploy the
    given anatomy to it. Assing the project to all users with
    defaultAccessGroups.

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

    start_time = time.monotonic()
    async with Postgres.acquire() as conn, conn.transaction():
        await project.save(transaction=conn)
        await assign_default_users_to_project(project.name, conn)

    end_time = time.monotonic()
    logging.debug(f"Deployed project {project.name} in {end_time - start_time:.2f}s")

    await dispatch_event(
        "entity.project.created",
        sender="ayon",
        project=project.name,
        user="",
        description=f"Created project {project.name}",
    )
