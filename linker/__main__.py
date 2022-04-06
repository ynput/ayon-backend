import asyncio

from linker.linker import make_links
from openpype.lib.postgres import Postgres

# Each link type has input and output descriptions.
# Resolver for both is the same and accepts the following:
#
#
# folder_path: regex to match folder path
# folder_type: type of folder (str)
# folder_id: only used internally to resolve "same_folder" argument
# subset_name: regex to match subset name
# limit: count of random objects to resolve (only makes sense on output)
#
# Top level parameter 'same_folder' limit the output section result
# to the same folder as the input.

LINK_TYPES = [
    "breakdown|subset|folder",
    "breakdown|folder|folder",
    "reference|version|version",
]

GEN_CONFIG = [
    {
        "link_type": "breakdown|subset|folder",
        "input": {
            "folder_type": "Asset",
            "folder_path": "^assets/characters/.*",
            "subset_name": "^model.*",
        },
        "output": {
            "subset_name": "^rigMain$",
            "limit": 20,
        },
        "same_folder": True,
    },
    {
        "link_type": "breakdown|folder|folder",
        "input": {
            "folder_type": "Asset",
            "folder_path": "^assets/characters/.*",
        },
        "output": {
            "folder_type": "Shot",
            "limit": 20,
        },
        "same_folder": False,
    },
    {
        "link_type": "reference|version|version",
        "input": {
            "folder_type": "Asset",
            "folder_path": "^assets/characters/.*",
            "subset_name": "^rigMain$",
        },
        "output": {
            "folder_type": "Shot",
            "subset_name": "^workfileCompositing$",
            "limit": 20,
        },
        "same_folder": False,
    },
]


async def create_link_type(
    project_name: str,
    link_type_name: str,
) -> None:

    link_type, input_type, output_type = link_type_name.split("|")

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
        await Postgres.execute(f"DELETE FROM project_{project_name}.links")

        if project_name.lower() != "demo_commercial":
            # DEBUG ON A SMALL PROJECT
            continue

        for link_type in LINK_TYPES:
            await create_link_type(project_name, link_type)

        for link_type_config in GEN_CONFIG:
            await make_links(project_name, link_type_config)


if __name__ == "__main__":
    asyncio.run(main())
