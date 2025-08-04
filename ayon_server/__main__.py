import importlib
import os
import sys

from ayon_server.cli import app
from ayon_server.logging import logger

CLI_PLUGINS_DIRS = [
    "cli",
    "/ayon-server-cli" "/storage/ayon-server-cli",
]


def main() -> None:
    for plugin_dir in CLI_PLUGINS_DIRS:
        if not os.path.isdir(plugin_dir):
            continue
        sys.path.insert(0, plugin_dir)
        for module_name in sorted(os.listdir(plugin_dir)):
            try:
                _ = importlib.import_module(module_name)
            except ImportError:
                logger.error(f"Unable to initialize {module_name}")
                continue
    app()


if __name__ == "__main__":
    main()
