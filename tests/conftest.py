import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from ayon_server.lib.postgres import Postgres  # noqa: E402


async def _noop(*args, **kwargs) -> None:
    pass


async def _undefined_table(*args, **kwargs) -> None:
    raise Postgres.UndefinedTableError("Database is not available in tests")


# The attribute library is loaded from the database when
# `ayon_server.entities` is imported. Tests run without a database,
# so the library falls back to the placeholder attribute list
# (the same as with an uninitialized database). Tests which need
# specific attributes replace them using `AttributeLibrary.reload`.
Postgres.connect = classmethod(_noop)  # type: ignore[assignment]
Postgres.shutdown = classmethod(_noop)  # type: ignore[assignment]
Postgres.fetch = classmethod(_undefined_table)  # type: ignore[assignment]
