from openpype.addons import ServerAddonDefinition


class ServerAddon(ServerAddonDefinition):
    """Ftrack integration"""

    name = "ftrack"
    addon_type = "module"
