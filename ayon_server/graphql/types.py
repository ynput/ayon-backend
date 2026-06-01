from typing import Any

import strawberry
from strawberry.types import Info as StrawberryInfo

Info = StrawberryInfo[dict[str, Any], None]

@strawberry.type
class ColumnStats:
    """Collector for statistical info about column values"""
    column_name: str

    value_filled_count: int
    percentage_filled: float

    value_not_filled_count: int
    percentage_not_filled: float

    checked_count: int
    checked_percentage: float

    not_checked_count: int
    not_checked_percentage: float

    avg: float | None = None
    min: float | None = None
    max: float | None = None


@strawberry.type
class PageInfo:
    has_next_page: bool = False
    has_previous_page: bool = False
    start_cursor: str | None = None
    end_cursor: str | None = None
    column_metadata: list[ColumnStats] | None = None


@strawberry.type
class BaseConnection:
    page_info: PageInfo = strawberry.field(
        default_factory=PageInfo, description="Pagination information"
    )


@strawberry.type
class BaseEdge:
    pass
