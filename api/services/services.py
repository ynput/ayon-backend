from fastapi import APIRouter, Depends

from openpype.api import ResponseFactory
from openpype.api.dependencies import dep_current_user
from openpype.entities import UserEntity
from openpype.lib.postgres import Postgres
from openpype.types import OPModel, Field


router = APIRouter(
    prefix="/services",
    tags=["Services"],
    responses={401: ResponseFactory.error(401)},
)


class ServiceModel(OPModel):
    id: int = Field(...)
    hostname: str = Field(..., example="worker03")
    addon_name: str = Field(..., example="ftrack")
    addon_version: str = Field(..., example="2.0.0")
    service_name: str = Field(..., example="collector")
    image: str = Field(..., example="openpype/ftrack-addon-collector:2.0.0")


class ServiceListModel(OPModel):
    services: list[ServiceModel] = Field(default_factory=list)


@router.get("", response_model=ServiceListModel)
async def list_services(user: UserEntity = Depends(dep_current_user)):

    services = [
        ServiceModel(**row)
        async for row in Postgres.iterate("SELECT * FROM services")
    ]

    return ServiceListModel(services=services)
