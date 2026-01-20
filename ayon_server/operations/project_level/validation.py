import datetime
from typing import Annotated, Any

from pydantic import Field, root_validator

from ayon_server.types import NAME_REGEX, OPModel
from ayon_server.utils import EntityID, slugify


class Subtask(OPModel):
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
    subtasks = payload_dict.get("data", {}).get("subtasks", [])

    if subtasks:
        result = []
        # min_start = None
        # max_end = None
        for subtask in subtasks:
            _subtask_obj = Subtask(**subtask)
            result.append(_subtask_obj.dict(exclude_none=True))

        # ensure unique IDs
        ids = set()
        for subtask in result:
            if subtask["id"] in ids:
                raise ValueError(f"Duplicate subtask ID {subtask['id']}")
            ids.add(subtask["id"])

        # ensure unique names
        names = set()
        for subtask in result:
            if subtask["name"] in names:
                raise ValueError(f"Duplicate subtask name {subtask['name']}")
            names.add(subtask["name"])

    else:
        payload_dict.get("data", {}).pop("subtasks", None)

    if not payload_dict.get("data", {}).get("subtaskSyncId"):
        payload_dict.get("data", {})["subtaskSyncId"] = None
