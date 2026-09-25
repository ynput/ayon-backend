from typing import Any

from fastapi.responses import ORJSONResponse, Response

from ayon_server.types import OPModel
from ayon_server.utils import EntityID


class JSONResponse(ORJSONResponse):
    pass


class ErrorResponse(OPModel):
    code: int
    detail: str


class EntityIdResponse(OPModel):
    id: str = EntityID.field()


class EmptyResponse(Response):
    def __init__(self, status_code: int = 204, **kwargs: Any) -> None:
        super().__init__(status_code=status_code, **kwargs)
