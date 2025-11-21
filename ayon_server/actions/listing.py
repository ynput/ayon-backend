from typing import Annotated

import aiocache

from ayon_server.actions.context import ActionContext
from ayon_server.actions.manifest import BaseActionManifest, SimpleActionManifest
from ayon_server.addons import AddonLibrary, BaseServerAddon
from ayon_server.entities import UserEntity
from ayon_server.events import EventModel, EventStream
from ayon_server.exceptions import NotFoundException
from ayon_server.lib.postgres import Postgres
from ayon_server.lib.redis import Redis
from ayon_server.logging import logger
from ayon_server.types import Field, OPModel
from ayon_server.utils import json_dumps, json_loads


class AvailableActionsListModel(OPModel):
    actions: Annotated[
        list[BaseActionManifest],
        Field(
            title="Available actions",
            default_factory=list,
            description="The list of available actions",
        ),
    ]


@aiocache.cached(ttl=60)
async def _load_relevant_addons(
    user_name: str,
    variant: str | None,
    is_developer: bool,
    user_last_modified: str,
) -> tuple[str, list[BaseServerAddon]]:
    query: tuple[str] | tuple[str, str]
    _ = user_last_modified  # this is used just to invalidate the cache

    if variant == "production":
        query = (
            "SELECT name, data->'addons' as addons FROM bundles WHERE is_production",
        )
    elif variant == "staging":
        query = ("SELECT name, data->'addons' as addons FROM bundles WHERE is_staging",)
    elif variant:
        query = (
            "SELECT name, data->'addons' as addons FROM bundles WHERE name = $1",
            variant,
        )

    elif is_developer:
        # get the list of addons from the development environment
        query = (
            """
            SELECT name, data->'addons' as addons FROM bundles
            WHERE is_dev AND active_user = $1""",
            user_name,
        )
    else:
        # get the list of addons from the production bundle
        query = (
            "SELECT name, data->'addons' as addons FROM bundles WHERE is_production",
        )
        variant = "production"

    res = await Postgres.fetch(*query)
    if not res:
        return "production", []

    result = []

    # if the variant is not already "production",
    # we use dev bundle name as the variant
    if variant is None:
        variant = res[0]["name"]

    for addon_name, addon_version in res[0]["addons"].items():
        if not addon_version:
            continue
        try:
            addon = AddonLibrary.addon(addon_name, addon_version)
        except NotFoundException:
            continue
        result.append(addon)
    return variant, result


async def get_relevant_addons(
    variant: str | None, user: UserEntity
) -> tuple[str, list[BaseServerAddon]]:
    """Get the list of addons that are relevant for the user.

    Normally it means addons in the production bundle,
    but if the user has developerMode enabled, it will return addons
    set up in their development environment.

    returns a tuple of variant and list of addons
    """
    is_developer = user.is_developer and user.attrib.developerMode
    user_last_modified = str(user.updated_at)

    return await _load_relevant_addons(
        user.name,
        variant,
        is_developer,
        user_last_modified,
    )


def match_list_subtypes(
    action_subtypes: list[str],
    context_subtypes: list[str],
) -> bool:
    """List matching

    ## action subtype (defined by manifest)

    - always includes the contained entity type (version, folder, etc.)
    - optionally includes the list type: "version:review-session"

    ## context subtypes (provided by the client)

    always includes both parts: "version:review-session"

    ## Matching Rules

    An action_subtype matches a context_subtype if:

    - The contained type matches (version == version)

    - And if action_subtype includes a list type,
      it must also match (review-session)

    - If action_subtype doesn't include a list type,
      it's considered a wildcard (matches all list types
      of that entity type)
    """
    for context_subtype in context_subtypes:
        context_parts = context_subtype.split(":", 1)
        context_entity = context_parts[0]
        context_list_type = context_parts[1] if len(context_parts) > 1 else None

        for action_subtype in action_subtypes:
            action_parts = action_subtype.split(":", 1)
            action_entity = action_parts[0]
            action_list_type = action_parts[1] if len(action_parts) > 1 else None

            if context_entity != action_entity:
                continue

            if action_list_type is None or action_list_type == context_list_type:
                return True

    return False


async def evaluate_simple_action(
    action: SimpleActionManifest,
    context: ActionContext,
) -> bool:
    """Evaluate if a simple action is available for a given context.

    This compares action entity_type, entity_subtypes and allow_muliselection
    attributes with the context and returns True if the action is available.
    """

    if action.entity_type != context.entity_type:
        return False

    if context.entity_type:
        if context.entity_type == "project" and context.project_name:
            # Project level actions are always available for the project context
            return True

        if not context.entity_ids:
            return False

        if not action.allow_multiselection and len(context.entity_ids) > 1:
            return False

        if action.entity_subtypes:
            if not context.entity_subtypes:
                return False

            if action.entity_type == "list":
                return match_list_subtypes(
                    action.entity_subtypes,
                    context.entity_subtypes,
                )

            # Normal project level entities. Just a simple subtype match:
            # if we have an overlapping subtype, we can run the action
            return bool(set(action.entity_subtypes) & set(context.entity_subtypes))

    return True


class SimpleActionCache:
    hooks_installed: bool = False
    ns: str = "addon_simple_actions"

    @classmethod
    async def handle_project_changed(cls, event: EventModel):
        keys = await Redis.keys(cls.ns)
        for key in keys:
            _, _, project_name, _ = key.split("|")
            if project_name == event.project:
                await Redis.delete(cls.ns, key)

    @classmethod
    async def handle_settings_changed(cls, event: EventModel):
        addon_name = event.summary["addon_name"]
        addon_version = event.summary["addon_version"]
        variant = event.summary["variant"]

        keys = await Redis.keys(cls.ns)
        for key in keys:
            addon, version, _, v = key.split("|")
            if addon == addon_name and version == addon_version and v == variant:
                await Redis.delete(cls.ns, key)

    @classmethod
    async def clear_action_cache(cls) -> None:
        logger.debug("Clearing actions cache")
        keys = await Redis.keys(cls.ns)
        for key in keys:
            await Redis.delete(cls.ns, key)

    @classmethod
    async def get(
        cls,
        addon: BaseServerAddon,
        project_name: str | None = None,
        variant: str = "production",
    ) -> list[SimpleActionManifest]:
        """Get a list of simple actions for a given context.

        This method is called for each addon to get a list of simple actions
        that can be performed on a given context. The context is defined by the
        project name and variant.

        The resulting list is then displayed to the user, who can choose to run
        one of the actions.
        """

        if not cls.hooks_installed:
            await cls.clear_action_cache()
            # This can be local hook, because no matter what replica
            # triggered the event, cached data will be updated in redis
            EventStream.subscribe("entity.project.changed", cls.handle_project_changed)
            EventStream.subscribe("settings.changed", cls.handle_settings_changed)
            cls.hooks_installed = True

        # The cache key
        cache_key = f"{addon.name}|{addon.version}|{project_name or ''}|{variant}"

        cached_data = await Redis.get(cls.ns, cache_key)
        if cached_data is None:
            r = await addon.get_simple_actions(project_name, variant)
            # Cache the data
            cached_data = [x.dict() for x in r]
            await Redis.set(cls.ns, cache_key, json_dumps(cached_data))
            # return the model
            return r

        return [SimpleActionManifest(**x) for x in json_loads(cached_data)]


async def get_action_whitelist(
    user: UserEntity,
    project_name: str | None,
) -> list[str] | None:
    if not user.is_manager:
        perms = user.permissions(project_name)
        if perms.actions.enabled:
            return perms.actions.actions
    return None


async def get_simple_actions(
    user: UserEntity,
    context: ActionContext,
    variant: str | None,
) -> AvailableActionsListModel:
    actions = []
    variant, addons = await get_relevant_addons(variant, user)
    project_name = context.project_name

    action_whitelist = await get_action_whitelist(user, project_name)

    for addon in addons:
        simple_actions = await SimpleActionCache.get(addon, project_name, variant)
        for action in simple_actions:
            if action.admin_only and not user.is_admin:
                continue

            if action.manager_only and not user.is_manager:
                continue

            if (
                action_whitelist is not None
                and action.identifier not in action_whitelist
            ):
                continue

            if await evaluate_simple_action(action, context):
                action.addon_name = addon.name
                action.addon_version = addon.version
                action.variant = variant
                actions.append(action)
    return AvailableActionsListModel(actions=actions)


async def get_dynamic_actions(
    user: UserEntity,
    context: ActionContext,
    variant: str | None,
) -> AvailableActionsListModel:
    """Get a list of dynamic actions for a given context.

    This method is called for each addon to get a list of dynamic actions
    that can be performed on a given context. The context is defined by the
    project name, entity type, and entity ids.

    The resulting list is then displayed to the user, who can choose to run
    one of the actions.
    """

    action_whitelist = await get_action_whitelist(
        user, project_name=context.project_name
    )

    actions = []
    variant, addons = await get_relevant_addons(variant, user)
    for addon in addons:
        for action in await addon.get_dynamic_actions(context, variant):
            if (
                action_whitelist is not None
                and action.identifier not in action_whitelist
            ):
                continue

            actions.append(action)

    return AvailableActionsListModel(actions=actions)
