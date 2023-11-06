import time

from pydantic import BaseModel, Field

from ayon_server.lib.postgres import Postgres

ConVal = int | bool


class ConstraintsModel(BaseModel):
    exp: int = Field(..., alias="exp")
    data: dict[str, ConVal] = Field(default_factory=dict, alias="data")


async def load_licenses() -> list[str]:
    res = await Postgres.fetch("SELECT value FROM config WHERE key = 'licenses'")
    if not res:
        return []
    return res[0]["value"]


class Constraints:
    constraints: ConstraintsModel | None = None
    parser = None

    @classmethod
    async def load(cls):
        if cls.parser is None:
            return
        lics = await load_licenses()
        cls.constraints = await cls.parser(lics)

    @classmethod
    async def check(cls, key: str) -> ConVal | None:
        if cls.parser is None:
            return None

        if cls.constraints is None or time.time() > cls.constraints.exp:
            await cls.load()

        assert cls.constraints is not None, "Licenses not loaded"
        return cls.constraints.data.get(key, False)
