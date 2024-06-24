from ayon_server.actions.context import ActionContext
from ayon_server.actions.manifest import BaseActionManifest, SimpleActionManifest
from ayon_server.addons import AddonLibrary, BaseServerAddon
from ayon_server.entities import UserEntity
from ayon_server.lib.postgres import Postgres
from ayon_server.types import Field, OPModel


class AvailableActionsListModel(OPModel):
    variant: str | None = Field(
        None,
        description="The variant of the bundle",
    )
    actions: list[BaseActionManifest] = Field(
        default_factory=list,
        description="The list of available actions",
    )


async def get_relevant_addons(user: UserEntity) -> tuple[str, list[BaseServerAddon]]:
    """Get the list of addons that are relevant for the user.

    Normally it means addons in the production bundle,
    but if the user has developerMode enabled, it will return addons
    set up in their development environment.

    returns a tuple of variant and list of addons
    """
    # TODO: This HAS TO BE cached somehow
    # because it is executed every time the user changes the selection

    is_developer = user.is_developer and user.attrib.developerMode
    variant = None

    if is_developer:
        # get the list of addons from the development environment
        query = (
            """
            SELECT name, data->'addons' as addons FROM bundles
            WHERE is_dev AND active_user = $1""",
            user.name,
        )
    else:
        # get the list of addons from the production bundle
        query = (
            "SELECT name, data->'addons' as addons FROM bundles WHERE is_production",
        )
        # we're in production mode
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
        addon = AddonLibrary.addon(addon_name, addon_version)
        if addon is None:
            continue
        result.append(addon)
    return variant, result


def evaluate_simple_action(
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
        if not context.entity_ids:
            return False

        if action.allow_multiselection and len(context.entity_ids) != 1:
            return False

        if action.entity_subtypes:
            pass  # TODO: implement this

    return True


async def get_simple_actions(
    user: UserEntity, context: ActionContext
) -> AvailableActionsListModel:
    actions = []
    variant, addons = await get_relevant_addons(user)
    for addon in addons:
        simple_actions = await addon.get_simple_actions()
        for action in simple_actions:
            if evaluate_simple_action(action, context):
                actions.append(action)
    return AvailableActionsListModel(variant=variant, actions=actions)


async def get_dynamic_actions(
    user: UserEntity,
    context: ActionContext,
) -> AvailableActionsListModel:
    """Get a list of dynamic actions for a given context.

    This method is called for each addon to get a list of dynamic actions
    that can be performed on a given context. The context is defined by the
    project name, entity type, and entity ids.

    The resulting list is then displayed to the user, who can choose to run
    one of the actions.
    """

    actions = []
    variant, addons = await get_relevant_addons(user)
    for addon in addons:
        actions.extend(await addon.get_dynamic_actions(context))
    return AvailableActionsListModel(variant=variant, actions=actions)
