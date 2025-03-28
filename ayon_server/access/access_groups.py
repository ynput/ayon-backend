import asyncio
from typing import TYPE_CHECKING, Any

from ayon_server.access.permissions import (
    AttributeAccessList,
    EndpointsAccessList,
    FolderAccess,
    FolderAccessList,
    Permissions,
)
from ayon_server.exceptions import NotFoundException
from ayon_server.helpers.project_list import get_project_list
from ayon_server.lib.postgres import Postgres
from ayon_server.lib.redis import Redis
from ayon_server.logging import logger
from ayon_server.types import normalize_to_dict

if TYPE_CHECKING:
    from ayon_server.events import EventModel


async def get_access_group(
    access_group_name: str, project_name: str = "_"
) -> Permissions:
    """Too bad we cannot use this :-(
    We need to access access group without async... but i'll keep this here for now.
    Who knows...
    """
    ns = "access-group"
    key = f"{access_group_name}:{project_name}"
    lock = asyncio.Lock()
    async with lock:
        if (data := await Redis.get_json(ns, key)) is None:
            schema = "public" if project_name == "_" else f"project_{project_name}"
            query = f" SELECT name, data FROM {schema}.access_groups WHERE name = $1"
            res = await Postgres.fetchrow(query, access_group_name)
            if res is None:
                raise NotFoundException(f"Access group '{access_group_name}' not found")
            data = dict(res)
            await Redis.set_json(ns, key, data)
    return Permissions.from_record(data)


class AccessGroups:
    access_groups: dict[tuple[str, str], Permissions] = {}

    @classmethod
    async def load(cls, *args, **kwargs) -> None:
        logger.trace(f"Loading access groups {args}")
        cls.access_groups = {}
        async for row in Postgres.iterate(
            "SELECT name, data FROM public.access_groups"
        ):
            cls.add_access_group(
                row["name"],
                "_",
                Permissions.from_record(row["data"]),
            )

        project_list = await get_project_list()
        for project in project_list:
            project_name = project.name
            async for row in Postgres.iterate(
                f"SELECT name, data FROM project_{project_name}.access_groups"
            ):
                cls.add_access_group(
                    row["name"],
                    project_name,
                    Permissions.from_record(row["data"]),
                )

    @classmethod
    async def update_hook(cls, event: "EventModel") -> None:
        if event.topic == "access_group.deleted":
            cls.access_groups.pop((event.summary["name"], event.project or "_"), None)
            return
        if event.topic != "access_group.updated":
            return
        schema = "public" if not event.project else f"project_{event.project}"
        name = event.summary["name"]
        query = f"SELECT data FROM {schema}.access_groups WHERE name = $1"
        res = await Postgres.fetchrow(query, name)
        if not res:
            logger.warning(f"Unable to update access group {name}: not found")
            return
        cls.access_groups[(name, event.project or "_")] = Permissions.from_record(
            res["data"]
        )
        suffix = f" for project {event.project}" if event.project else ""
        logger.debug(f"Updated access group {name}{suffix}")

    @classmethod
    def add_access_group(
        cls, name: str, project_name: str, permissions: Permissions
    ) -> None:
        cls.access_groups[(name, project_name)] = permissions

    @classmethod
    def combine(
        cls, access_group_names: list[str], project_name: str = "_"
    ) -> Permissions:
        """Create aggregated permissions object for a given list of access_groups.

        If a project name is specified and there is a project-level override
        for a given access group, it will be used.
        Ohterwise a "_" (default) access group will be used.
        """

        result: dict[str, Any] | None = None

        for access_group_name in access_group_names:
            if (access_group_name, project_name) in cls.access_groups:
                access_group = cls.access_groups[(access_group_name, project_name)]
            elif (access_group_name, "_") in cls.access_groups:
                access_group = cls.access_groups[(access_group_name, "_")]
            else:
                continue

            if result is None:
                result = access_group.dict()
                continue

            for perm_name, value in access_group:
                if hasattr(value, "enabled"):
                    if not value.enabled:
                        result[perm_name] = {"enabled": False}
                        continue
                    elif not result[perm_name]["enabled"]:
                        continue

                if perm_name in ["project", "studio"]:
                    for k, v in result.get(perm_name, {}).items():
                        old_value = result[perm_name].get(k, 0)
                        new_value = value.__getattribute__(k)
                        if isinstance(v, bool | int):
                            result[perm_name][k] = max(old_value, new_value)

                elif perm_name in ("create", "read", "update", "delete"):
                    # TODO: deduplicate
                    assert isinstance(value, FolderAccessList)
                    result[perm_name]["access_list"] = list(
                        {
                            FolderAccess(**normalize_to_dict(r))
                            for r in result[perm_name].get("access_list", [])
                        }
                        | set(value.access_list)
                    )

                elif perm_name in ("attrib_read", "attrib_write"):
                    assert isinstance(value, AttributeAccessList)
                    result[perm_name]["attributes"] = list(
                        set(result[perm_name].get("attributes", []))
                        | set(value.attributes)
                    )
                elif perm_name == "endpoints":
                    assert isinstance(value, EndpointsAccessList)
                    result[perm_name]["endpoints"] = list(
                        set(result[perm_name].get("endpoints", []))
                        | set(value.endpoints)
                    )

        if not result:
            return Permissions()
        return Permissions(**result)
