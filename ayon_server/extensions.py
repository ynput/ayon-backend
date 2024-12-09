import os

from nxtools import log_traceback, logging

from ayon_server.helpers.modules import classes_from_module, import_module


class ServerExtension:
    async def initialize(self):
        pass


async def init_extensions():
    if not os.path.isdir("/extensions"):
        return

    for file in os.listdir("/extensions"):
        try:
            module = import_module(file[:-3], f"/extensions/{file}")
        except Exception:
            log_traceback()
            continue

        classes = classes_from_module(ServerExtension, module)
        for cls in classes:
            logging.info(f"Initializing extension {cls.__name__}")
            await cls().initialize()
