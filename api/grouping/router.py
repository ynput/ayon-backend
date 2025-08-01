from fastapi import APIRouter

from ayon_server.config import ayonconfig

router = APIRouter(
    prefix="/projects/{project_name}/grouping",
    tags=["Grouping"],
    include_in_schema=ayonconfig.openapi_include_internal_endpoints,
)
