from ayon_server.lib.postgres import Postgres


async def get_event_count_per_topic() -> dict[str, int]:
    result = {}
    query = "SELECT topic, COUNT(*) as count FROM events GROUP BY topic"
    async for row in Postgres.iterate(query):
        result[row["topic"]] = row["count"]
    return result
