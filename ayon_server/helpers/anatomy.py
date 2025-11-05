from ayon_server.entities import ProjectEntity
from ayon_server.helpers.extract_anatomy import extract_project_anatomy
from ayon_server.lib.redis import Redis
from ayon_server.settings.anatomy import Anatomy


async def get_project_anatomy(project_name: str) -> Anatomy:
    if cached_data := await Redis.get_json("project-anatomy", project_name):
        return Anatomy(**cached_data)

    project = await ProjectEntity.load(project_name)
    anatomy = extract_project_anatomy(project)
    await Redis.set_json("project-anatomy", project_name, anatomy.dict(), ttl=3600)
    return anatomy
