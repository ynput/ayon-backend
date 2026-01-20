import datetime
import time
from typing import Annotated, Any

from pydantic import Field, root_validator

from ayon_server.types import NAME_REGEX, OPModel
from ayon_server.utils import EntityID, slugify


class Subtask(OPModel):
    """Validation model used to define and validate individual task subtasks.

    This model represents a single subtask entry within a task payload and is
    used by task validation routines to ensure that subtask identifiers,
    names, labels, and optional scheduling metadata are well-formed and
    consistent.
    """

    id: Annotated[str, Field(**EntityID.META, default_factory=EntityID.create)]
    name: Annotated[
        str,
        Field(
            title="Subtask name",
            example="Modeling",
            regex=NAME_REGEX,
        ),
    ]
    label: Annotated[str, Field(title="Subtask label", example="Modeling")]

    @root_validator(pre=True)
    def validate_name(cls, values: dict[str, Any]) -> dict[str, Any]:
        value = values.get("name", "").strip()
        if not value:
            value = slugify(values.get("label", "").strip(), separator="_")
        if not value:
            raise ValueError("Subtask name/label cannot be empty")
        values["name"] = value
        return values

    description: Annotated[
        str | None,
        Field(
            title="Subtask description",
            example="Modeling subtask for the asset",
            max_length=2048,
        ),
    ] = None

    start_date: Annotated[
        datetime.datetime | None,
        Field(
            title="Subtask start date",
            example="2024-01-01T09:00:00Z",
        ),
    ] = None

    end_date: Annotated[
        datetime.datetime | None,
        Field(
            title="Subtask end date",
            example="2024-01-15T18:00:00Z",
        ),
    ] = None


def validate_task(payload_dict: dict[str, Any]) -> None:
    """Validate and normalize task subtasks in the given payload.

    This function inspects the ``data.subtasks`` list in ``payload_dict``, uses
    the :class:`Subtask` model to validate and normalize each subtask entry,
    and enforces uniqueness of subtask ``id`` and ``name`` values. If the
    list is empty or missing, the ``subtasks`` key is removed from the
    ``data`` mapping. Additionally, if ``data.subtaskSyncId`` is falsy or
    missing, it is set explicitly to ``None``.

    The input ``payload_dict`` is mutated in place; the function does not
    return a value.

    Args:
        payload_dict: A dictionary representing the task payload, expected to
            contain a ``"data"`` key with optional ``"subtasks"`` and
            ``"subtaskSyncId"`` entries.

    Raises:
        ValueError: If any subtask is invalid according to :class:`Subtask`
            validation, or if there are duplicate subtask IDs or names.
    """
    if "data" not in payload_dict:
        # nothing in data, so neither subtasks or subtaskSyncId
        return

    if "subtasks" not in payload_dict["data"]:
        # nothing to validate
        return

    subtasks = payload_dict["data"].get("subtasks", [])

    if subtasks:
        result = []
        for subtask in subtasks:
            _subtask_obj = Subtask(**subtask)
            result.append(_subtask_obj.dict(exclude_none=True))

        # ensure unique IDs and names
        ids = set()
        names = set()
        for subtask in result:
            if subtask["id"] in ids:
                raise ValueError(f"Duplicate subtask ID {subtask['id']}")
            if subtask["name"] in names:
                raise ValueError(f"Duplicate subtask name {subtask['name']}")
            ids.add(subtask["id"])
            names.add(subtask["name"])

        payload_dict["data"]["subtasks"] = result

        if "subtaskSyncId" not in payload_dict["data"]:
            payload_dict["data"]["subtaskSyncId"] = time.time()
