from typing import Any

from ayon_server.enum.base_resolver import BaseEnumResolver
from ayon_server.enum.enum_item import EnumItem
from ayon_server.exceptions import ForbiddenException
from ayon_server.forms.simple_form import SimpleForm
from ayon_server.lib.postgres import Postgres
from ayon_server.models import IconModel
from ayon_server.types import AttributeType
from ayon_server.utils import SQLTool


class ProjectsEnumResolver(BaseEnumResolver):
    """List of projects the user has access to."""

    name = "projects"
    label = "Projects"

    async def get_accepted_params(self) -> dict[str, AttributeType]:
        return {
            "include_inactive": "boolean",
            "include_library": "boolean",
            "include_skeleton": "boolean",
        }

    async def get_settings_form(self) -> SimpleForm | None:
        return (
            SimpleForm()
            .boolean("include_inactive", "Include inactive projects", False)
            .boolean("include_library", "Include library projects", True)
            .boolean("include_skeleton", "Include skeleton projects", False)
        )

    async def resolve(self, context: dict[str, Any]) -> list[EnumItem]:
        user = context.get("user")

        # No user = system process, sees all.
        can_list_all = user is None
        if user is not None:
            try:
                user.check_permissions("studio.create_projects")
                can_list_all = True
            except ForbiddenException:
                pass

        conditions = []
        if not context.get("include_inactive", False):
            conditions.append("active IS TRUE")
        if not context.get("include_library", True):
            conditions.append("library IS FALSE")
        if not context.get("include_skeleton", False):
            conditions.append("data->>'isSkeleton' IS DISTINCT FROM 'true'")

        query = f"""
            SELECT
                name, code, label, active, updated_at,
                data->>'color' AS color,
                data->'guestUsers' AS guest_users
            FROM public.projects
            {SQLTool.conditions(conditions)}
            ORDER BY active DESC, name
        """

        result: list[EnumItem] = []
        for row in await Postgres.fetch(query):
            name = row["name"]
            if user is not None:
                # guest check first: legacy guests must not see all projects
                if user.is_guest:
                    if user.attrib.email not in (row["guest_users"] or {}):
                        continue
                if not can_list_all:
                    access_groups = user.data.get("accessGroups", {})
                    if not isinstance(access_groups, dict):
                        continue
                    if not access_groups.get(name):
                        continue

            # URL only - the client fetches (and caches) the image lazily.
            # updated_at is bumped on thumbnail upload, so it busts the cache.
            ts = int(row["updated_at"].timestamp())
            result.append(
                EnumItem(
                    value=name,
                    label=row["label"] or name,
                    short_name=row["code"],
                    color=row["color"] or None,
                    icon=IconModel(
                        type="url",
                        url=f"/api/projects/{name}/thumbnail?t={ts}",
                    ),
                )
            )
        return result
