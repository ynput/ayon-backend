#!/usr/bin/env python3

import json
from pprint import pprint
from typing import Any

from ayon_server.exceptions import ConflictException
from ayon_server.initialize import ayon_init
from ayon_server.lib.postgres import Postgres
from ayon_server.operations.project_level import ProjectLevelOperations

PROJECT_NAME = "inheritance2"
ENTITY_ID = "e9f6afcef77a49ed82df58d833599816"


def jsonify(val):
    return json.dumps(val)


def build_update_query(
    entity_id: str,
    table: str,
    data: dict[str, Any],
    jsonb_columns: set[str] | None = None,
) -> tuple[str, list[Any]]:
    jsonb_columns = jsonb_columns or set()

    sets = []
    params = []

    param_index = 1

    for key, value in data.items():
        if key in jsonb_columns and isinstance(value, dict):
            # JSONB columns handling

            json_expr = f"COALESCE({key}, '{{}}'::jsonb)"

            # First handle all jsonb_set calls
            for subkey, subval in value.items():
                if subval is not None:
                    json_expr = f"jsonb_set({json_expr}, '{{{subkey}}}', ${param_index}::jsonb, true)"  # noqa
                    params.append(subval)
                    param_index += 1

            # Then handle removals (value = None removes the key)
            for subkey, subval in value.items():
                if subval is None:
                    json_expr = f"{json_expr} - '{subkey}'"

            sets.append(f"{key} = {json_expr}")

        else:
            sets.append(f"{key} = ${param_index}")
            params.append(value)
            param_index += 1

    query = f"UPDATE {table} SET " + ", ".join(sets) + f" WHERE id = ${param_index}"
    params.append(entity_id)

    return query, params


async def check_entity_content():
    res = await Postgres.fetchrow(
        f"SELECT * FROM project_{PROJECT_NAME}.folders WHERE id = $1", ENTITY_ID
    )
    if res is None:
        raise ValueError("Entity not found")
    pprint(dict(res))


async def main():
    await ayon_init(extensions=False)

    entity_id = "12345"
    table = "my_table"

    data = {
        "name": "New Name",
        "age": 30,
        "details": {
            "address": "123 Main St",
            "phone": None,  # This will be removed
        },
    }

    jsonb_columns = {"details"}
    query, params = build_update_query(entity_id, table, data, jsonb_columns)
    print("Generated Query:", query)
    print("Parameters:", params)

    try:
        try:
            ops = ProjectLevelOperations(PROJECT_NAME)
            ops.create(
                "folder",
                entity_id=ENTITY_ID,
                name="my_updte_test",
                folder_type="Folder",
                tags=["abc", "def"],
                data={
                    "my_key": "my_value",
                    "other_key": "other_value",
                    "very_other_key": "very_other_value",
                },
            )
            await ops.process()
        except ConflictException:
            print("Entity already exists, proceeding with update.")

        # Check the content

        payload: dict[str, Any] = {
            "folderType": "Asset",
            "tags": ["abc", "def", "ghi"],
            "status": "On hold",
            "data": {
                "my_key": "updated_value",
                "other_key": None,  # This will be removed
                "very_other_key": None,
                "new_key": "new_value",
                "a_number": 42,
                "a_dict": {"foo": "bar"},
            },
        }

        ops = ProjectLevelOperations(PROJECT_NAME)
        ops.update(
            "folder",
            entity_id=ENTITY_ID,
            **payload,
        )
        await ops.process()

        # query, params = build_update_query(
        #     ENTITY_ID,
        #     f"project_{PROJECT_NAME}.folders",
        #     payload,
        #     jsonb_columns={"data"},
        # )

        # print("Update Query:", query)
        #
        # await Postgres.execute(query, *params)

        await check_entity_content()

    finally:
        await Postgres.execute(
            f"DELETE FROM project_{PROJECT_NAME}.folders WHERE id = $1", ENTITY_ID
        )


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
