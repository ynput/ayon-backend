from ayon_server.lib.postgres import Postgres


class Secrets:
    @classmethod
    async def get(cls, key: str) -> str | None:
        """
        Get a secret. Return None if it doesn't exist.
        """
        query = "SELECT value FROM public.secrets WHERE name = $1"
        res = await Postgres.fetch(query, key)
        if not res:
            return None
        return res[0]["value"]

    @classmethod
    async def set(cls, key: str, value: str):
        """
        Set a secret. Create it if it doesn't exist.
        """
        query = """
            INSERT INTO public.secrets (name, value) VALUES ($1, $2)
            ON CONFLICT (name) DO UPDATE SET value = $2
        """
        await Postgres.execute(query, key, value)

    @classmethod
    async def delete(cls, key: str):
        """
        Delete a secret.
        """
        query = "DELETE FROM public.secrets WHERE name = $1"
        await Postgres.execute(query, key)

    @classmethod
    async def all(cls) -> dict[str, str]:
        """
        Return a dictionary of all secrets.
        """
        query = "SELECT * FROM public.secrets"
        res = await Postgres.fetch(query)
        return {row["name"]: row["value"] for row in res}
