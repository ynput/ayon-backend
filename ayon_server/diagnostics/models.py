from datetime import UTC, datetime
from typing import Any, Literal

from ayon_server.models import RestField, RestModel

Severity = Literal["info", "warning", "critical"]
SEVERITY_ORDER: dict[str, int] = {"critical": 0, "warning": 1, "info": 2}


class Finding(RestModel):
    code: str = RestField(..., example="PG-STATS-001")
    severity: Severity = RestField(...)
    component: str = RestField(..., example="postgres")
    params: dict[str, Any] = RestField(default_factory=dict)
    detected_at: datetime = RestField(default_factory=lambda: datetime.now(UTC))


class CodeInfo(RestModel):
    """Human readable explanation of a finding code.

    `description` is a template filled in from the finding params.
    """

    title: str
    description: str
    explanation: str
    remediation: str
    docs: str | None = None
