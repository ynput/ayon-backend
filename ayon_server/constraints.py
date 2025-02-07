import time
from collections.abc import Awaitable, Callable

from pydantic import BaseModel, Field

from ayon_server.lib.postgres import Postgres

ConVal = int | bool


def now() -> int:
    return int(time.time())


class StatusModel(BaseModel):
    exp: int = Field(default_factory=now, alias="exp")
    sub: str = Field("unknown")
    val: ConVal = Field(False)
    valid: bool = Field(False)
    message: str = Field("unknown")


class ConstraintsModel(BaseModel):
    instance_id: str | None = Field(None)
    exp: int = Field(default_factory=now, alias="exp")
    data: dict[str, ConVal] = Field(default_factory=dict, alias="data")
    status: list[StatusModel] = Field(default_factory=list, alias="status")


async def load_licenses() -> list[str]:
    res = await Postgres.fetch("SELECT value FROM config WHERE key = 'licenses'")
    if not res:
        return []
    return res[0]["value"]


class Constraints:
    constraints: ConstraintsModel | None = None
    parser: Callable[[list[str]], Awaitable[ConstraintsModel]] | None = None

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
