import asyncio

from nxtools import logging

from ayon_server.entities.folder import FolderEntity
from ayon_server.entities.project import ProjectEntity
from ayon_server.helpers.deploy_project import create_project_from_anatomy
from ayon_server.helpers.hierarchy_restore import hierarchy_restore
from ayon_server.helpers.project_list import get_project_list
from ayon_server.initialize import ayon_init
from ayon_server.settings.anatomy import Anatomy

TARGET_PROJECT_NAME = "clonetest"
TARGET_PROJECT_CODE = "cln"
DUMP_PATH = "/storage/dump.zip"


async def main(project_name: str, project_code: str, dump_path: str) -> None:
    """Main entry point for setup."""

    await ayon_init()

    project_list = await get_project_list()
    if project_name in [project.name for project in project_list]:
        logging.debug(f"Project {project_name} already exists, deleting it.")
        project = await ProjectEntity.load(project_name)
        await project.delete()

    anatomy = Anatomy()
    await create_project_from_anatomy(project_name, project_code, anatomy)
    logging.debug(f"Project {project_name} created.")

    # create a bunch of root folders

    for i in range(3):
        payload = {
            "name": f"root_{i}",
            "folder_type": "Folder",
        }
        folder = FolderEntity(project_name, payload=payload)
        await folder.save()
        root_id = folder.id

        await hierarchy_restore(
            project_name,
            dump_path,
            reindex_entities=True,
            root=root_id,
        )


if __name__ == "__main__":
    asyncio.run(main(TARGET_PROJECT_NAME, TARGET_PROJECT_CODE, DUMP_PATH))
