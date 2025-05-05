from ayon_server.api.dependencies import CurrentUser, ProjectName
from ayon_server.lib.postgres import Postgres
from ayon_server.logging import logger
from ayon_server.types import OPModel

from .router import router


class ProjectTagsModel(OPModel):
    folders: list[str]
    tasks: list[str]
    products: list[str]
    versions: list[str]
    representations: list[str]
    workfiles: list[str]


@router.get("/projects/{project_name}/tags")
async def get_project_tags(
    user: CurrentUser,
    project_name: ProjectName,
) -> ProjectTagsModel:
    """List tags used in the project."""

    query = """
        select jsonb_object_agg(table_name, tags_array) as res
        from (
          select 'folders' as table_name, array_agg(distinct tag) as tags_array
          from folders, unnest(folders.tags) as tag

          union all

          select 'tasks', array_agg(distinct tag)
          from tasks, unnest(tasks.tags) as tag

          union all

          select 'products', array_agg(distinct tag)
          from products, unnest(products.tags) as tag

          union all

          select 'versions', array_agg(distinct tag)
          from versions, unnest(versions.tags) as tag

          union all

          select 'representations', array_agg(distinct tag)
          from representations, unnest(representations.tags) as tag

          union all

          select 'workfiles', array_agg(distinct tag)
          from workfiles, unnest(workfiles.tags) as tag
        ) sub;

        """

    async with Postgres.acquire() as conn, conn.transaction():
        await conn.execute(f"set local search_path to project_{project_name}")
        result = await conn.fetchrow(query)

        result = dict(result["res"]) if result else {}
        logger.debug(f"{result}")

        return ProjectTagsModel(**result)
