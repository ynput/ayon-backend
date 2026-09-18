from ayon_server.entities import ProjectEntity
from ayon_server.helpers.extract_anatomy import extract_project_anatomy
from ayon_server.lib.redis import Redis
from ayon_server.settings.anatomy import Anatomy
from ayon_server.settings.anatomy.link_types import default_link_types


async def get_project_anatomy(project_name: str) -> Anatomy:
    if cached_data := await Redis.get_json("project-anatomy", project_name):
        anatomy = Anatomy(**cached_data)
        if all(dlt in anatomy.link_types for dlt in default_link_types):
            return anatomy

        # cache predates the required-link-types backfill (or was populated
        # before a since-invalidated project-data cache caught up) - drop it
        # and fall through to a fresh load, which self-heals via
        # ensure_required_project_link_types
        await Redis.delete("project-anatomy", project_name)

    project = await ProjectEntity.load(project_name)
    anatomy = extract_project_anatomy(project)
    await Redis.set_json("project-anatomy", project_name, anatomy.dict(), ttl=3600)
    return anatomy
