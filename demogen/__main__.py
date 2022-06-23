import asyncio
import json
import sys

from nxtools import critical_error, log_traceback, logging

from demogen.demogen import DemoGen
from openpype.entities.project import ProjectEntity
from openpype.exceptions import NotFoundException
from openpype.helpers.deploy_project import create_project_from_anatomy
from openpype.lib.postgres import Postgres
from openpype.settings.anatomy import Anatomy


async def main() -> None:
    data = sys.stdin.read()
    if not data:
        critical_error("No data provided")

    try:
        project_template = json.loads(data)
    except Exception:
        log_traceback()
        critical_error("Invalid project data provided")

    anatomy = Anatomy()
    project_name = project_template["name"]
    project_hierarchy = project_template["hierarchy"]

    logging.info("Connecting to database")
    await Postgres.connect()

    logging.info("Deleting project")
    try:
        project = await ProjectEntity.load(project_name)
    except NotFoundException:
        pass
    else:
        await project.delete()
        logging.info(f"Project {project_name} deleted")

    await create_project_from_anatomy(
        name=project_template["name"],
        code=project_template["code"],
        anatomy=anatomy,
    )

    demo = DemoGen(validate=True)
    await demo.populate(project_name, project_hierarchy)


if __name__ == "__main__":
    asyncio.run(main())
