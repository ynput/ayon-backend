import strawberry

from openpype.utils import json_loads


def parse_json_data(target_type, json_string):
    data = json_loads(json_string)
    if not data:
        return target_type()
    result = {}
    for key in target_type.__dataclass_fields__.keys():
        if key in data:
            result[key] = data[key]
    return target_type(**result)


def lazy_type(name: str, module: str) -> strawberry.LazyType:
    """Create a lazy type for the given module and name.

    When used, module path must be relative
    to THIS file (root of the graphql module)
    e.g. `.nodes.node` or `.connection`
    """
    return strawberry.LazyType[name, module]
