from ayon_server.attributes.fix_attribute_values import fix_attribute_values
from ayon_server.cli import app
from ayon_server.initialize import ayon_init


@app.command()
async def fix_attributes(
    project_name: str | None = None,
    attribute: list[str] | None = None,
    dry_run: bool = False,
) -> None:
    """Fix attribute values, which are not valid for their definitions.

    Values are converted when possible, otherwise they are removed.
    Without --project-name, all projects and users are checked.
    Without --attribute, all attributes are checked.
    With --dry-run, the changes are only reported.
    """
    await ayon_init()
    await fix_attribute_values(project_name, attribute_names=attribute, dry_run=dry_run)
