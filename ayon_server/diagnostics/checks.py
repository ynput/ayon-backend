import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from ayon_server.logging import logger

from .models import SEVERITY_ORDER, CodeInfo, Finding

CHECK_TIMEOUT = 15  # seconds, per check

CheckFunction = Callable[[], Awaitable[list[Finding]]]


@dataclass(frozen=True)
class Check:
    component: str
    name: str
    func: CheckFunction


CODES: dict[str, CodeInfo] = {}
CHECKS: list[Check] = []


def register_code(code: str, info: CodeInfo) -> None:
    # Codes are never reused, so a second registration is a bug
    assert code not in CODES, f"Diagnostic code {code} is already registered"
    CODES[code] = info


def diagnostic_check(component: str) -> Callable[[CheckFunction], CheckFunction]:
    """Register a read-only check returning a list of findings."""

    def decorator(func: CheckFunction) -> CheckFunction:
        CHECKS.append(Check(component, func.__name__, func))
        return func

    return decorator


register_code(
    "DIAG-CHECK-FAILED",
    CodeInfo(
        title="Diagnostic check failed",
        description="Check {check} failed: {error}",
        explanation=(
            "The check could not finish, so the problems it looks for "
            "may be present but were not detected."
        ),
        remediation="Look at the server log for the full error.",
    ),
)


async def _run_check(check: Check) -> list[Finding]:
    try:
        return await asyncio.wait_for(check.func(), CHECK_TIMEOUT)
    except Exception as e:
        logger.warning(f"Diagnostic check {check.component}.{check.name} failed: {e}")
        error = str(e) or e.__class__.__name__
        return [
            Finding(
                code="DIAG-CHECK-FAILED",
                severity="warning",
                component=check.component,
                params={"check": f"{check.component}.{check.name}", "error": error},
            )
        ]


async def run_checks(components: list[str] | None = None) -> list[Finding]:
    """Run the registered checks and return findings, most severe first."""
    findings: list[Finding] = []
    # One check at a time: diagnostics must not add load to a struggling server
    for check in CHECKS:
        if components is None or check.component in components:
            findings.extend(await _run_check(check))
    findings.sort(key=lambda f: SEVERITY_ORDER[f.severity])
    return findings
