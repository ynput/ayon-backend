import importlib.util
import inspect
import os
import sys
from types import ModuleType
from typing import TypeVar

T = TypeVar("T", bound=type)


def import_module(name: str, path: str) -> ModuleType:
    """
    Imports a plugin module into a unique namespace to prevent collisions.

    The ``name`` argument is an arbitrary unique identifier used as the
    module's namespace (i.e. the key in ``sys.modules``). It does not have
    to be a valid dotted Python package path and may contain characters
    like ``-`` or ``/``.

    Examples:
        - ``f"{vname}-package"`` (e.g. ``"my-addon-package"``)
        - ``"ayon_server/enum/resolvers"``
    """

    server_dir = os.path.dirname(os.path.abspath(path))  # Directory containing the module
    # Determine which directory should be added to sys.path:
    # - If the module is inside a 'server' package, add its parent (the 'version' folder)
    #   so that 'server' is importable as a top-level package.
    # - Otherwise, add the module's own directory to avoid inserting overly broad paths.
    if os.path.basename(server_dir) == "server":
        base_dir = os.path.dirname(server_dir)
    else:
        base_dir = server_dir

    # Add the dir containing the module (or its parent, for 'server' packages) to sys.path temporarily.
    # This allows: 'from server.subfolder import module' in addons when appropriate.
    sys.path.insert(0, base_dir)

    try:
        spec = importlib.util.spec_from_file_location(name, path)
        if spec is None or spec.loader is None:
            raise ImportError(f"Could not load spec for {name}")

        module = importlib.util.module_from_spec(spec)

        # tell the module it belongs to our unique namespace
        # Even if the file is physically in 'server/main.py'
        sys.modules[name] = module

        spec.loader.exec_module(module)
        return module

    finally:
        # Clean up sys.path immediately so the next addon doesn't
        # accidentally see this plugin's 'server' folder.
        if base_dir in sys.path:
            sys.path.remove(base_dir)


def classes_from_module(superclass: T, module: ModuleType) -> list[T]:
    """Return plug-ins from module

    Arguments:
        superclass (superclass): Superclass of subclasses to look for
        module (types.ModuleType): Imported module from which to
            parse valid plug-ins.

    Returns:
        List of plug-ins, or empty list if none is found.

    """

    classes = []
    for name in dir(module):
        # It could be anything at this point
        obj = getattr(module, name)
        if not inspect.isclass(obj) or obj is superclass:
            continue

        if issubclass(obj, superclass):
            classes.append(obj)

    return classes  # type: ignore
