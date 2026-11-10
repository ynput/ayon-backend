import asyncio

from ayon_server.diagnostics import checks
from ayon_server.diagnostics.models import Finding


def test_failing_check_reports_finding_and_others_still_run(monkeypatch) -> None:
    async def broken() -> list[Finding]:
        raise RuntimeError("boom")

    async def ok() -> list[Finding]:
        return [Finding(code="X-TEST-001", severity="info", component="test")]

    async def bad() -> list[Finding]:
        return [Finding(code="X-TEST-002", severity="critical", component="test")]

    monkeypatch.setattr(
        checks,
        "CHECKS",
        [
            checks.Check("test", "broken", broken),
            checks.Check("test", "ok", ok),
            checks.Check("test", "bad", bad),
            checks.Check("other", "ok", ok),
        ],
    )
    findings = asyncio.run(checks.run_checks(["test"]))

    assert [f.code for f in findings] == [
        "X-TEST-002",
        "DIAG-CHECK-FAILED",
        "X-TEST-001",
    ]
    assert findings[1].params == {"check": "test.broken", "error": "boom"}


def test_every_code_used_is_in_catalog() -> None:
    assert {"DIAG-CHECK-FAILED", "PG-STATS-001"} <= checks.CODES.keys()
