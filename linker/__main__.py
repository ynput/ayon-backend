import asyncio

from linker.linker import make_links
from openpype.lib.postgres import Postgres

LINK_TYPES = [
    ["breakdown", "subset", "folder"],
    ["breakdown", "folder", "folder"],
    ["generative", "version", "version"],
    ["reference", "version", "version"],
]


async def create_link_type(
    project_name: str,
    link_type: str,
    input_type: str,
    output_type: str,
) -> str:

    link_type_name = f"{link_type}|{input_type}|{output_type}"

    await Postgres.execute(
        f"""
        INSERT INTO project_{project_name}.link_types
            (name, input_type, output_type, link_type)
        VALUES
            ($1, $2, $3, $4)
        """,
        link_type_name,
        input_type,
        output_type,
        link_type,
    )


async def main():
    await Postgres.connect()
    project_names = [
        row["name"] async for row in Postgres.iterate("SELECT name FROM projects")
    ]

    for project_name in project_names:
        await Postgres.execute(f"DELETE FROM project_{project_name}.link_types")
        for link_type in LINK_TYPES:
            await create_link_type(project_name, *link_type)

        for link_type in LINK_TYPES:
            await make_links(project_name, *link_type)


if __name__ == "__main__":
    asyncio.run(main())
