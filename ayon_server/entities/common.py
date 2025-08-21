from typing import Any

from ayon_server.exceptions import (
    NotFoundException,
    ServiceUnavailableException,
)
from ayon_server.lib.postgres import Postgres


async def query_entity_data(query: str, entity_id: str) -> dict[str, Any]:
    try:
        record = await Postgres.fetchrow(query, entity_id)
    except Postgres.UndefinedTableError as e:
        raise NotFoundException("Project does not exist or is not initialized.") from e
    except Postgres.LockNotAvailableError as e:
        raise ServiceUnavailableException(
            f"Entity {entity_id} is locked for update."
        ) from e
    if record is None:
        raise NotFoundException(f"Entity {entity_id} not found")
    return dict(record)
