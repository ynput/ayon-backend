import json
import sys
from typing import Any

import asyncpg

from ayon_server.cli import app
from ayon_server.lib.postgres import Postgres


class HealthCheckError(Exception):
    """Custom exception for health check errors."""

    pass


async def ensure_postgres_connection(result: dict[str, Any]) -> None:
    try:
        await Postgres.connect()
    except ConnectionRefusedError as e:
        result["status"] = "failed"
        result["error"] = "PostgreSQL connection refused"
        result["details"] = str(e)

    except asyncpg.exceptions.CannotConnectNowError as e:
        result["status"] = "failed"
        result["error"] = "PostgreSQL cannot connect now"
        result["details"] = str(e)

    except Exception as e:
        result["status"] = "failed"
        result["error"] = "PostgreSQL connection error"
        result["details"] = str(e)

    else:
        result["checks"]["postgres_connected"] = True

    result["checks"]["postgres_available_connections"] = (
        Postgres.get_available_connections()
    )

    raise HealthCheckError()


@app.command()
async def healthcheck() -> None:
    """Check the health of the AYON Server."""
    result = {"status": "ok", "checks": {}}

    try:
        await ensure_postgres_connection(result)

    except HealthCheckError:
        status_code = 1
    else:
        status_code = 0

    print(json.dumps(result, indent=2))
    sys.exit(status_code)
