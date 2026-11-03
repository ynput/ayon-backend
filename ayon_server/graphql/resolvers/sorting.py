from collections.abc import Callable
from typing import Any

from ayon_server.entities import ProjectEntity
from ayon_server.entities.core.attrib import attribute_library
from ayon_server.exceptions import BadRequestException


def _literal(value: Any) -> str:
    """Return the value as a quoted SQL string literal"""
    return "'" + str(value).replace("'", "''") + "'"


def get_task_types_sort_case(project: ProjectEntity) -> str:
    """
    Get a SQL CASE expression to sort by task types
    in the order they are defined in the project anatomy.
    """

    task_type_names = [r["name"] for r in project.task_types]
    if not task_type_names:
        return "tasks.task_type"
    case = "CASE"
    for i, task_type_name in enumerate(task_type_names):
        case += f" WHEN tasks.task_type = {_literal(task_type_name)} THEN {i}"
    case += f" ELSE {i + 1}"
    case += " END"
    return case


def get_folder_types_sort_case(project: ProjectEntity) -> str:
    """
    Get a SQL CASE expression to sort by folder types
    in the order they are defined in the project anatomy.
    """

    folder_type_names = [r["name"] for r in project.folder_types]
    if not folder_type_names:
        return "folders.folder_type"
    case = "CASE"
    for i, folder_type_name in enumerate(folder_type_names):
        case += f" WHEN folders.folder_type = {_literal(folder_type_name)} THEN {i}"
    case += f" ELSE {i + 1}"
    case += " END"
    return case


def get_status_sort_case(project: ProjectEntity, exp: str) -> str:
    """
    Get a SQL CASE expression to sort by statuses
    in the order they are defined in the project anatomy.
    """

    status_names = [r["name"] for r in project.statuses]
    if not status_names:
        return "tasks.status"
    case = "CASE"
    for i, status_name in enumerate(status_names):
        case += f" WHEN {exp} = {_literal(status_name)} THEN {i}"
    case += f" ELSE {i + 1}"
    case += " END"
    return case


async def get_attrib_sort_case(attr: str, exp: str | Callable[[str], str]) -> str:
    if not attr.isidentifier():
        raise BadRequestException("Invalid attribute name")
    value = f"({exp(attr)}) #>> '{{}}'" if callable(exp) else f"{exp}->>'{attr}'"
    try:
        attr_data = attribute_library.by_name(attr)
    except KeyError:
        return value

    attr_type = attr_data.get("type")
    if attr_type == "integer":
        return f"({value})::bigint"
    if attr_type == "float":
        return f"({value})::double precision"

    enum = attr_data.get("enum", [])
    if not enum:
        return value
    case = "CASE"
    i = 0
    for i, eval in enumerate(enum):
        e = _literal(eval["value"])
        case += f" WHEN {value} = {e} THEN {i}"
    case += f" ELSE {i + 1}"
    case += " END"
    return case
