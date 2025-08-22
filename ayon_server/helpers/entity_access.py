from typing import Any

from ayon_server.access.utils import ensure_entity_access
from ayon_server.entities import ProjectEntity, UserEntity
from ayon_server.entities.core.projectlevel import ProjectLevelEntity
from ayon_server.exceptions import ForbiddenException
from ayon_server.lib.postgres import Postgres
from ayon_server.types import AccessType, OPModel


class ShareOption(OPModel):
    share_type: str
    value: str
    name: str
    label: str
    attribute: str | None = None


class EntityAccessHelper:
    NO_ACCESS = 0
    READ = 10
    UPDATE = 20
    MANAGE = 30

    @classmethod
    async def check(
        cls,
        user: UserEntity,
        *,
        access: dict[str, Any] | None = None,
        level: int = 0,
        owner: str | None = None,
        project: ProjectEntity | None = None,
        default_open: bool = True,
    ) -> None:
        _ = access, user, level, owner

        if owner and user.name == owner:
            return

        if default_open:
            return

        raise ForbiddenException()

    @classmethod
    async def get_share_options(
        cls,
        user: UserEntity,
        project_name: str | None = None,
    ) -> list[ShareOption]:
        query = """
            SELECT share_type, name, label, value
            FROM public.share_options
            WHERE user_name = $1 AND project_name = $2
        """
        try:
            res = await Postgres.fetch(
                query,
                user.name,
                project_name,
            )
        except Postgres.UndefinedTableError:
            raise NotImplementedError("Sharing module is not installed.")

        if not res:
            return []
        return [
            ShareOption(
                share_type=row["share_type"],
                name=row["value"],
                label=row["label"],
                value=row["value"],
            )
            for row in res
        ]

    @classmethod
    async def ensure_entity_access(
        cls,
        user: UserEntity,
        entity: ProjectLevelEntity,
        level: int = READ,
    ) -> None:
        """Ensure that the user has the required access level to the entity."""

        _level: AccessType

        if level >= cls.MANAGE:
            _level = "delete"
        elif level >= cls.UPDATE:
            _level = "update"
        elif level >= cls.READ:
            _level = "read"
        else:
            return

        await ensure_entity_access(
            user,
            entity.project_name,
            entity.entity_type,
            entity.id,
            _level,
        )
