import importlib.util
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
