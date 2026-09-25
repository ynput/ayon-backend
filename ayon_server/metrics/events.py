from ayon_server.lib.postgres import Postgres


async def get_event_count_per_topic(
    saturated: bool = False, system: bool = False
) -> dict[str, int]:
    """Return the count of events per topic.

    This helps us with optimization of event clean-up,
    and other maintenance tasks.
    """
    result = {}
    query = "SELECT topic, COUNT(*) as count FROM public.events GROUP BY topic"
    async for row in Postgres.iterate(query):
        result[row["topic"]] = row["count"]
    return result
