import json
import sys
from collections import Counter
from typing import Any

import typer
from typer import Option

from ayon_server.cli import app
from ayon_server.diagnostics.models import CodeInfo, Finding
from ayon_server.lib.postgres import Postgres

SEVERITY_COLORS = {"critical": "red", "warning": "yellow", "info": "blue"}


def format_item(item: Any) -> str:
    if not isinstance(item, dict):
        return str(item)
    first, *rest = item.items()
    details = ", ".join(f"{k}={v}" for k, v in rest)
    return f"{first[1]} ({details})" if details else str(first[1])


def format_finding(finding: Finding, info: CodeInfo) -> str:
    severity = typer.style(
        finding.severity.upper(), fg=SEVERITY_COLORS[finding.severity], bold=True
    )
    lines = [
        f"[{severity}] {finding.code}: {info.title}",
        f"  {info.description.format(**finding.params)}",
    ]
    for value in finding.params.values():
        if isinstance(value, list):
            lines += [f"    - {format_item(item)}" for item in value]
            if (more := finding.params.get("count", 0) - len(value)) > 0:
                lines.append(f"    ... and {more} more")
    lines += ["", f"  Why it matters: {info.explanation}", f"  Fix: {info.remediation}"]
    if info.docs:
        lines.append(f"  Docs: {info.docs}")
    return "\n".join(lines)


@app.command()
async def diagnostics(
    component: list[str] | None = Option(None, help="Limit to a component"),
    as_json: bool = Option(False, "--json", help="Print findings as JSON"),
) -> None:
    """Run read-only diagnostic checks. Exits with 1 on critical findings."""
    from ayon_server.diagnostics import CODES, run_checks

    await Postgres.connect()
    try:
        findings = await run_checks(component or None)
    finally:
        await Postgres.shutdown()

    if as_json:
        print(json.dumps([f.model_dump(mode="json") for f in findings], indent=2))
    elif not findings:
        typer.echo("No problems found.")
    else:
        for finding in findings:
            typer.echo(format_finding(finding, CODES[finding.code]) + "\n")
        counts = Counter(f.severity for f in findings)
        typer.echo(", ".join(f"{n} {severity}" for severity, n in counts.items()))
    sys.exit(1 if any(f.severity == "critical" for f in findings) else 0)
