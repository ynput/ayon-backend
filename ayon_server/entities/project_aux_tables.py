from collections.abc import Sequence
from typing import Literal, NotRequired, Required, TypedDict, overload

from ayon_server.entities.models.submodels import LinkTypeModel
from ayon_server.lib.postgres import Postgres

FolderTypesLiteral = Literal["folder_types"]
TaskTypesLiteral = Literal["task_types"]
StatusesLiteral = Literal["statuses"]
TagsLiteral = Literal["tags"]

State = Literal["not_started", "in_progress", "done", "blocked"]


class BaseAuxTable(TypedDict):
    name: Required[str]
    original_name: NotRequired[str]  # for renaming


class FolderTypeDict(BaseAuxTable):
    shortName: NotRequired[str]
    icon: NotRequired[str]
    color: NotRequired[str]


class TaskTypeDict(BaseAuxTable):
    shortName: NotRequired[str]
    icon: NotRequired[str]
    color: NotRequired[str]


class TagTypeDict(BaseAuxTable):
    color: NotRequired[str]


class StatusTypeDict(BaseAuxTable):
    shortName: NotRequired[str]
    state: NotRequired[State]
    icon: NotRequired[str]
    color: NotRequired[str]
    scope: NotRequired[list[str]]


AuxTableType = FolderTypeDict | TaskTypeDict | TagTypeDict | StatusTypeDict


@overload
async def aux_table_update(
    project_name: str,
    table: FolderTypesLiteral,
    update_data: Sequence[FolderTypeDict],
) -> None: ...


@overload
async def aux_table_update(
    project_name: str,
    table: TaskTypesLiteral,
    update_data: Sequence[TaskTypeDict],
) -> None: ...


@overload
async def aux_table_update(
    project_name: str,
    table: StatusesLiteral,
    update_data: Sequence[StatusTypeDict],
) -> None: ...


@overload
async def aux_table_update(
    project_name: str, table: TagsLiteral, update_data: Sequence[TagTypeDict]
) -> None: ...


async def aux_table_update(
    project_name: str, table: str, update_data: Sequence[AuxTableType]
) -> None:
    """Update auxiliary table."""

    # Fetch the current data first
    old_data = {}
    for row in await Postgres.fetch(
        f"SELECT name, data FROM project_{project_name}.{table} ORDER BY position"
    ):
        old_data[row["name"]] = row["data"]

    position = 0
    for data in update_data:
        position += 1
        name = data.get("name")

        # Rename
        original_name = data.pop("original_name", None)
        if original_name and (original_name in old_data) and name != original_name:
            await Postgres.execute(
                f"""
                UPDATE project_{project_name}.{table}
                SET name = $1, position = $2, data = $3
                WHERE name = $4
                """,
                name,
                position,
                data,
                original_name,
            )

            del old_data[original_name]
            continue

        # Upsert
        await Postgres.execute(
            f"""
            INSERT INTO project_{project_name}.{table}
                (name, position, data)
            VALUES
                ($1, $2, $3)
            ON CONFLICT (name) DO UPDATE SET
                position = $2, data = $3
            """,
            name,
            position,
            data,
        )

        if name in old_data:
            del old_data[name]

    # Delete the rest
    if old_data:
        old_keys = list(old_data.keys())
        query = f"DELETE FROM project_{project_name}.{table} WHERE name = ANY($1)"
        await Postgres.execute(query, old_keys)


async def link_types_update(
    project_name: str,
    table: str,
    update_data: Sequence[LinkTypeModel],
):
    existing_names: list[str] = []
    for row in await Postgres.fetch(f"SELECT name FROM project_{project_name}.{table}"):
        existing_names.append(row["name"])

    new_names: list[str] = []
    for link_type_data in update_data or []:
        name = "|".join(
            [
                link_type_data.link_type,
                link_type_data.input_type,
                link_type_data.output_type,
            ]
        )
        new_names.append(name)

        # Upsert
        await Postgres.execute(
            f"""
            INSERT INTO project_{project_name}.{table}
                (name, link_type, input_type, output_type, data)
            VALUES
                ($1, $2, $3, $4, $5)
            ON CONFLICT (name) DO UPDATE SET
                link_type = $2, input_type = $3, output_type = $4, data = $5
            """,
            name,
            link_type_data.link_type,
            link_type_data.input_type,
            link_type_data.output_type,
            link_type_data.data,
        )

    for name in existing_names:
        if name not in new_names:
            await Postgres.execute(
                f"DELETE FROM project_{project_name}.{table} WHERE name = $1", name
            )
