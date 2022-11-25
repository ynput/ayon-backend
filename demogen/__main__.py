import asyncio
import json
import random
import sys

from nxtools import critical_error, log_traceback, logging

from demogen.demogen import DemoGen
from openpype.helpers.deploy_project import create_project_from_anatomy
from openpype.lib.postgres import Postgres
from openpype.settings.anatomy import Anatomy
from openpype.settings.anatomy.tags import Tag


def create_color() -> str:
    """Return a random color visible on dark background"""
    color = [random.randint(0, 255) for _ in range(3)]
    if sum(color) < 400:
        color = [255 - x for x in color]
    return f'#{"".join([f"{x:02x}" for x in color])}'


def generate_tags() -> list[Tag]:
    pool = """
    beauty cute funny happy sad scary sexy
    cuddly fluffy soft warm fuzzy hairy furry
    spiky sharp pointy dangerous adorable
    flabadob blip blup blip boo
    """
    names: list[str] = [r.strip() for r in pool.split() if r.strip()]
    tags: list[Tag] = []
    for name in names:
        tags.append(
            Tag(
                name=name,
                color=create_color(),
                original_name=name,
            )
        )
    return tags


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

    anatomy.tags = generate_tags()

    project_name = project_template["name"]
    project_hierarchy = project_template["hierarchy"]

    logging.info("Connecting to database")
    await Postgres.connect()

    logging.info("Deleting old project if exists")
    await Postgres.execute(f"DROP SCHEMA IF EXISTS project_{project_name} CASCADE")
    await Postgres.execute("DELETE FROM projects WHERE name = $1", project_name)

    await create_project_from_anatomy(
        name=project_template["name"],
        code=project_template["code"],
        anatomy=anatomy,
    )

    demo = DemoGen(validate=True)
    await demo.populate(project_name, project_hierarchy)


if __name__ == "__main__":
    asyncio.run(main())
