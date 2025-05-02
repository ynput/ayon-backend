from datetime import datetime

from ayon_server.utils import EntityID, json_dumps, json_loads


def timestamptz_endocder(v):
    if isinstance(v, int | float):
        return datetime.fromtimestamp(v).isoformat()
    if isinstance(v, datetime):
        return v.isoformat()
    if isinstance(v, str):
        return datetime.fromisoformat(v).isoformat()
    raise ValueError


def timestamptz_decoder(v):
    if isinstance(v, int | float):
        return datetime.fromtimestamp(v)
    if isinstance(v, datetime):
        return v
    if isinstance(v, str):
        return datetime.fromisoformat(v)
    raise ValueError


async def postgres_setup(cls, conn) -> None:
    """Set up the connection pool"""
    await conn.set_type_codec(
        "jsonb",
        encoder=json_dumps,
        decoder=json_loads,
        schema="pg_catalog",
    )
    await conn.set_type_codec(
        "uuid",
        encoder=lambda x: EntityID.parse(x, True),
        decoder=lambda x: EntityID.parse(x, True),
        schema="pg_catalog",
    )

    await conn.set_type_codec(
        "timestamptz",
        encoder=timestamptz_endocder,
        decoder=timestamptz_decoder,
        schema="pg_catalog",
    )
