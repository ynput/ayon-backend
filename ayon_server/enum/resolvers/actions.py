from typing import Any

from ayon_server.addons.library import AddonLibrary
from ayon_server.enum.base_resolver import BaseEnumResolver
from ayon_server.enum.enum_item import EnumItem
from ayon_server.lib.postgres import Postgres


class ActionsEnumResolver(BaseEnumResolver):
    name = "actions"

    async def get_accepted_params(self) -> dict[str, type]:
        return {"project_name": str}

    async def resolve(self, context: dict[str, Any]) -> list[EnumItem]:
        action_idents = set()
        result: list[EnumItem] = []

        bundles = await Postgres.fetch(
            """
            SELECT name, is_production, is_staging, is_dev, data
            FROM public.bundles
            """
        )
        for bundle in bundles:
            if (
                bundle["is_production"]
                or bundle["is_staging"]
                or bundle["is_dev"]
                or bundle["data"].get("is_project")
            ):
                for addon_name, addon_version in (
                    bundle["data"].get("addons", {}).items()
                ):
                    try:
                        addon = AddonLibrary.addon(addon_name, addon_version)
                    except Exception:
                        continue

                    actions = await addon.get_simple_actions()
                    for action in actions:
                        if action.identifier in action_idents:
                            continue

                        action_idents.add(action.identifier)
                        result.append(
                            EnumItem(
                                value=action.identifier,
                                label=f"{action.label} ({addon.name}/{action.identifier})",  # noqa: E501
                                group=addon_name,
                                icon=action.icon,
                            )
                        )

        result.sort(key=lambda x: f"{x.group}{x.value}" or "")
        return result
