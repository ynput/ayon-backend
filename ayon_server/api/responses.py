from http import HTTPStatus
from typing import Any

from fastapi.responses import ORJSONResponse

from ayon_server.types import OPModel
from ayon_server.utils import EntityID


class JSONResponse(ORJSONResponse):
    pass


class ErrorResponse(OPModel):
    code: int
    detail: str


class EntityIdResponse(OPModel):
    id: str = EntityID.field()


class ResponseFactory:
    @classmethod
    def error(cls, code: int = 500, detail: str | None = None) -> dict[str, Any]:
        detail = detail or {401: "Not logged in", 403: "Access denied"}.get(
            code, HTTPStatus(code).name.capitalize()
        )

        return {
            "model": ErrorResponse,
            "description": detail,
            "content": {
                "application/json": {"example": {"code": code, "detail": detail}}
            },
        }
