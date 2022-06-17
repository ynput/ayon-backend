import importlib.util
import inspect
import sys
from types import ModuleType


def import_module(name: str, path: str) -> ModuleType:
    if (spec := importlib.util.spec_from_file_location(name, path)) is None:
        raise ModuleNotFoundError(f"Module {name} not found")
    if (module := importlib.util.module_from_spec(spec)) is None:
        raise ImportError(f"Module {name} cannot be imported")
    if spec.loader is None:
        raise ImportError(f"Module {name} cannot be imported. No loader found.")
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def classes_from_module(superclass, module: ModuleType) -> list:
    """Return plug-ins from module

    Arguments:
        superclass (superclass): Superclass of subclasses to look for
        module (types.ModuleType): Imported module from which to
            parse valid plug-ins.

    Returns:
        List of plug-ins, or empty list if none is found.

    """

    classes = list()
    for name in dir(module):
        # It could be anything at this point
        obj = getattr(module, name)
        if not inspect.isclass(obj) or obj is superclass:
            continue

        if issubclass(obj, superclass):
            classes.append(obj)

    return classes
