from typing import Literal

from ayon_server.lib.postgres import Postgres

UsageType = Literal["ingress", "egress"]


async def update_traffic_stats(
    usage_type: UsageType,
    value: int,
    service: str = "ayon",
) -> None:
    if usage_type not in ["ingress", "egress"]:
        raise ValueError("Invalid usage type")
    query = f"""
       INSERT INTO public.traffic_stats (date, service, {usage_type})
       VALUES (current_date, $1, $2)
       ON CONFLICT (date, service)
       DO UPDATE SET {usage_type} = traffic_stats.{usage_type} + $2
    """
    await Postgres().execute(query, service, value)
