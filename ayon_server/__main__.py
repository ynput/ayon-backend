import importlib
import os
import sys

from ayon_server.cli import app
from ayon_server.logging import logger


def main() -> None:
    plugin_dir = "cli"
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
