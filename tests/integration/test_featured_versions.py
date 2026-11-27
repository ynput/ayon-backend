"""The featured version expression used by entity list items, in Postgres.

Everything runs in a project schema created in a transaction,
which is rolled back at the end.
"""

from typing import Any

import pytest

from ayon_server.lib.postgres import Postgres

PROJECT = "test_featured_versions"

# product, version, status. Creation order follows the list order.
VERSIONS = [
    # p1: v3 is the newest, v2 the newest done, a hero points to v1
    ("p1", 1, "Approved"),
    ("p1", 2, "Approved"),
    ("p1", 3, "In progress"),
    ("p1", -1, "Approved"),
    # p2: nothing is done and there is no hero
    ("p2", 1, "In progress"),
    ("p2", 2, "In progress"),
]

STATUSES = {"Approved": "done", "In progress": "in_progress"}


class Rollback(Exception):
    pass


def _uuid(name: str) -> str:
    return name.encode().hex().ljust(32, "0")


def _hex(value: Any) -> str | None:
    # asyncpg returns UUID objects, the AYON codec may return strings
    return str(value).replace("-", "") if value is not None else None


async def _create_project() -> None:
    await Postgres.execute(f"CREATE SCHEMA project_{PROJECT}")
    await Postgres.execute(f"SET LOCAL search_path TO project_{PROJECT}")
    with open("schemas/schema.project.sql") as f:
        await Postgres.execute(f.read())
    await Postgres.set_project_schema(PROJECT)
    await Postgres.execute("INSERT INTO folder_types (name) VALUES ('Folder')")
    for name, state in STATUSES.items():
        await Postgres.execute(
            "INSERT INTO statuses (name, data) VALUES ($1, $2)", name, {"state": state}
        )
    await Postgres.execute(
        """
        INSERT INTO folders (id, name, folder_type, status)
        VALUES ($1, 'shot', 'Folder', 'Approved')
        """,
        _uuid("folder"),
    )
    for product in ("p1", "p2"):
        await Postgres.execute(
            """
            INSERT INTO products (id, name, folder_id, product_type, status)
            VALUES ($1, $2, $3, 'render', 'Approved')
            """,
            _uuid(product),
            product,
            _uuid("folder"),
        )
    for product, version, status in VERSIONS:
        await Postgres.execute(
            """
            INSERT INTO versions (id, product_id, version, status)
            VALUES ($1, $2, $3, $4)
            """,
            _uuid(f"{product}v{version}"),
            _uuid(product),
            version,
            status,
        )


async def _featured(flags: list[str]) -> dict[str | None, str | None]:
    from ayon_server.graphql.resolvers.featured_versions import (
        featured_version_id_expression,
    )

    result: dict[str | None, str | None] = {}
    try:
        async with Postgres.transaction():
            await _create_project()
            expr = featured_version_id_expression(PROJECT, flags, "e")
            rows = await Postgres.fetch(
                f"""
                SELECT DISTINCT e.product_id, {expr} AS featured
                FROM project_{PROJECT}.versions e
                """
            )
            result = {_hex(r["product_id"]): _hex(r["featured"]) for r in rows}
            raise Rollback()
    except Rollback:
        pass
    return result


def _id(product: str, version: int | None) -> str | None:
    if version is None:
        return None
    return _uuid(f"{product}v{version}")


@pytest.mark.parametrize(
    "flags, p1, p2",
    [
        (["latest"], 3, 2),
        (["latestDone"], 2, None),
        (["hero"], 1, None),
        (["latestDone", "latest"], 2, 2),
        (["hero", "latestDone", "latest"], 1, 2),
        (["latest", "hero"], 3, 2),
    ],
)
def test_featured_version_per_product(run, flags, p1, p2):
    assert run(_featured(flags)) == {
        _uuid("p1"): _id("p1", p1),
        _uuid("p2"): _id("p2", p2),
    }
