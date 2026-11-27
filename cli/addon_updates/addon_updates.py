import json
import sys

from typer import Option

from ayon_server.cli import app
from ayon_server.helpers.cloud import CloudUtils
from ayon_server.lib.postgres import Postgres


@app.command()
async def addon_updates(
    bundle: str | None = Option(None, help="Bundle name (default: production)"),
    blacklist: list[str] | None = Option(None, help="Addon not to update"),
) -> None:
    """Print addon updates Ynput Cloud offers for a bundle. Changes nothing."""

    await Postgres.connect()
    try:
        if bundle:
            query = "SELECT name, data FROM public.bundles WHERE name = $1"
            row = await Postgres.fetchrow(query, bundle)
        else:
            query = "SELECT name, data FROM public.bundles WHERE is_production"
            row = await Postgres.fetchrow(query)
        if not row:
            sys.exit(f"Bundle {bundle or '(production)'} not found")

        addons = {k: v for k, v in (row["data"].get("addons") or {}).items() if v}
        updates = await CloudUtils.get_addon_updates(addons, blacklist)
    finally:
        await Postgres.shutdown()

    result = [{**u, "current": addons.get(u["name"])} for u in updates]
    print(json.dumps({"bundle": row["name"], "updates": result}, indent=2))
