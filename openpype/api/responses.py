from http import HTTPStatus
from pydantic import BaseModel
from fastapi.responses import ORJSONResponse


class JSONResponse(ORJSONResponse):
    pass


class ErrorResponse(BaseModel):
    code: int
    detail: str


class ResponseFactory:
    models = {}

    @classmethod
    def error(cls, code: int = 500, detail: str = None):
        detail = detail or {401: "Not logged in", 403: "Access denied"}.get(
            code, HTTPStatus(code).name.capitalize()
        )

        return {
            "model": ErrorResponse,
            "description": detail,
            "content": {
                "application/json": {
                    "example": {"code": code, "detail": detail}
                }
            },
        }
