import builtins
import importlib.util
import inspect
import os
import sys
from types import ModuleType
from typing import Any

# Registry of addon namespaces: unique_name -> addon_base_dir
_ADDON_REGISTRY: dict[str, str] = {}
_original_import = builtins.__import__

# Addons importing `pydantic` get a Pydantic 1 compatible layer
PYDANTIC_COMPAT_MODULE = "ayon_server.settings.pydantic_compat"


def _find_addon_namespace(mod_name: str) -> str | None:
    """Return the registered addon namespace the module belongs to"""
    # This is called for every import statement executed at runtime,
    # so use dict lookups of the module name prefixes instead of
    # iterating over all registered addons.
    if mod_name in _ADDON_REGISTRY:
        return mod_name
    end = mod_name.find(".")
    while end != -1:
        prefix = mod_name[:end]
        if prefix in _ADDON_REGISTRY:
            return prefix
        end = mod_name.find(".", end + 1)
    return None


def _isolated_import(
    name: str,
    globals: dict[str, Any] | None = None,
    locals: dict[str, Any] | None = None,
    fromlist: tuple[str, ...] = (),
    level: int = 0,
):
    """
    Custom __import__ that redirects 'server' and other addon-local imports
    to the unique addon namespace.
    """

    if level > 0:
        # Relative import, let it be
        return _original_import(name, globals, locals, fromlist, level)

    mod_name = globals.get("__name__") if globals else None
    if not mod_name:
        try:
            f = sys._getframe(1)
            while f:
                mod_name = f.f_globals.get("__name__")
                if mod_name:
                    break
                f = f.f_back  # type: ignore[assignment]
        except ValueError:
            pass

    if mod_name and _ADDON_REGISTRY:
        addon_name = _find_addon_namespace(mod_name)
        if addon_name:
            target_name = None
            if name == "pydantic":
                target_name = PYDANTIC_COMPAT_MODULE
            elif name == "server" or name.startswith("server."):
                target_name = f"{addon_name}.{name}"
            else:
                base_dir = _ADDON_REGISTRY[addon_name]
                if os.path.exists(os.path.join(base_dir, name)) or os.path.exists(
                    os.path.join(base_dir, name + ".py")
                ):
                    target_name = f"{addon_name}.{name}"

            if target_name:
                if fromlist:
                    return _original_import(
                        target_name, globals, locals, fromlist, level
                    )
                else:
                    return importlib.import_module(target_name)

    return _original_import(name, globals, locals, fromlist, level)


# Global patch
builtins.__import__ = _isolated_import  # type: ignore[assignment]


def import_module(name: str, path: str) -> ModuleType:
    """
    Imports a plugin module into a unique namespace to prevent collisions.
    Example: 'my-addon-v1-0-0.server'
    """

    server_dir = os.path.dirname(os.path.abspath(path))
    if os.path.basename(server_dir) == "server":
        base_dir = os.path.dirname(server_dir)
    else:
        base_dir = server_dir

    # Only register for isolation if name is a valid python identifier
    if name.replace("-", "_").replace(".", "_").isidentifier():
        _ADDON_REGISTRY[name] = base_dir

    # Ensure the root package for the unique name exists
    if name not in sys.modules:
        root_module = ModuleType(name)
        root_module.__path__ = [base_dir]
        sys.modules[name] = root_module

    # Load the actual entry point as name.server (or just name if not a server package)
    if os.path.basename(server_dir) == "server":
        module_name = f"{name}.server"
    else:
        module_name = name

    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load spec for {module_name}")

    if path.endswith("__init__.py"):
        spec.submodule_search_locations = [server_dir]

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)

    return module


def classes_from_module[T: type](superclass: T, module: ModuleType) -> list[T]:
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
