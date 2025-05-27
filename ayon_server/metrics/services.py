from ayon_server.lib.postgres import Postgres
from ayon_server.types import Field, OPModel


class ServiceInfo(OPModel):
    addon_name: str = Field(..., title="Addon name", example="kitsu")
    addon_version: str = Field(..., title="Addon version", example="1.0.0")
    service_name: str = Field(..., title="Service name", example="processor")


async def get_active_services(
    saturated: bool = False, system: bool = False
) -> list[ServiceInfo]:
    """List of active services"""

    query = """
    SELECT addon_name, addon_version, service
    FROM public.services WHERE should_run is true;
    """

    result = []
    async for row in Postgres.iterate(query):
        result.append(
            ServiceInfo(
                addon_name=row["addon_name"],
                addon_version=row["addon_version"],
                service_name=row["service"],
            )
        )

    return result
