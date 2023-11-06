import time

from ayon_server.lib.postgres import Postgres

ConVal = int | bool


async def load_licenses() -> list[str]:
    res = await Postgres.fetch("SELECT value FROM config WHERE key = 'licenses'")
    if not res:
        return []
    return res[0]["value"]


class Constraints:
    expires: int = 0
    data: dict[str, ConVal] | None = None
    parser = None

    @classmethod
    async def load(cls):
        if cls.parser is None:
            return
        lics = await load_licenses()
        cls.data = await cls.parser(lics)

    @classmethod
    async def check(cls, key: str) -> ConVal | None:
        if cls.parser is None:
            return None

        if cls.data is None or time.time() > cls.expires:
            await cls.load()

        assert cls.data is not None, "Licenses not loaded"

        if key not in cls.data:
            return False

        return cls.data["key"]
