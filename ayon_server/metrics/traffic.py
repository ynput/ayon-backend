from ayon_server.lib.postgres import Postgres
from ayon_server.types import OPModel


class TrafficStat(OPModel):
    date: str
    service: str
    ingress: int
    egress: int


async def get_traffic_stats(
    saturated: bool = False,
    system: bool = False,
) -> list[TrafficStat] | None:
    _ = saturated
    if not system:
        # Collect traffic stats only when we collect system metrics
        return None

    result = []
    query = "SELECT * FROM public.traffic_stats ORDER BY date DESC limit 65"
    async for row in Postgres.iterate(query):
        date = row["date"].strftime("%Y-%m-%d")
        service = row["service"]
        ingress = row["ingress"]
        egress = row["egress"]
        result.append(
            TrafficStat(
                date=date,
                service=service,
                ingress=ingress,
                egress=egress,
            )
        )

    return result
