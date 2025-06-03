from typing import Annotated, Any

from ayon_server.types import Field, OPModel


class EntityGroup(OPModel):
    value: Annotated[
        Any,
        Field(
            title="Entity grouping Value",
            description="The value used for grouping entities.",
            example=["john.doe"],
        ),
    ]

    label: Annotated[
        str | None,
        Field(
            title="Task Grouping Label",
            description="A label for the grouping, if applicable.",
            example="John Doe",
        ),
    ] = None

    icon: Annotated[
        str | None,
        Field(
            title="Task Grouping Icon",
            description="An icon representing the grouping, if applicable.",
            example="user",
        ),
    ] = None

    color: Annotated[
        str | None,
        Field(
            title="Task Grouping Color",
            description="A color associated with the grouping, if applicable.",
            example="#FF5733",
        ),
    ] = None

    count: Annotated[
        int,
        Field(
            title="Task Count",
            description="The number of tasks in this grouping.",
            example=42,
        ),
    ] = 0
