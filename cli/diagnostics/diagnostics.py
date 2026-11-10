import json
import sys

from typer import Option

from ayon_server.cli import app
from ayon_server.lib.postgres import Postgres


@app.command()
async def diagnostics(
    component: list[str] | None = Option(None, help="Limit to a component"),
) -> None:
    """Run read-only diagnostic checks. Exits with 1 on critical findings."""
    from ayon_server.diagnostics import run_checks

    await Postgres.connect()
    try:
        findings = await run_checks(component or None)
    finally:
        await Postgres.shutdown()

    print(json.dumps([f.model_dump(mode="json") for f in findings], indent=2))
    sys.exit(1 if any(f.severity == "critical" for f in findings) else 0)
