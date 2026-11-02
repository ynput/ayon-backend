"""Private preferences of the current user.

Frontend and desktop tools store their state under their own namespaced
key (e.g. `io.ynput.core.browser`), either globally or per project
(selected by the `project_name` query parameter).

Preferences are only accessible to the user who owns them. There is
no way to address preferences of another user, admins and managers included.
"""

from datetime import datetime
from typing import Annotated, Any

from fastapi import Body, Path, Query

from ayon_server.api.dependencies import CurrentUser
from ayon_server.api.responses import EmptyResponse
from ayon_server.exceptions import BadRequestException, NotFoundException
from ayon_server.lib.postgres import Postgres
from ayon_server.types import PROJECT_NAME_REGEX, Field, OPModel

from .router import router

# Namespaced identifier, e.g. "io.ynput.core.browser"
PREFERENCE_KEY_REGEX = r"^[a-zA-Z0-9_]([a-zA-Z0-9_\.\-]{0,126}[a-zA-Z0-9_])?$"

# Maximum size of the serialized preference data (bytes)
MAX_PREFERENCE_SIZE = 256 * 1024


PPreferenceKey = Annotated[
    str,
    Path(
        title="Preference key",
        pattern=PREFERENCE_KEY_REGEX,
        examples=["io.ynput.core.browser"],
    ),
]

QProjectName = Annotated[
    str | None,
    Query(
        title="Project name",
        description="Project scope. Global preferences are used if omitted.",
        pattern=PROJECT_NAME_REGEX,
        examples=["my_project"],
    ),
]

PreferenceData = Annotated[
    dict[str, Any],
    Body(
        title="Preference data",
        examples=[{"columns": ["name", "status"], "showThumbnails": True}],
    ),
]


class PreferenceModel(OPModel):
    key: Annotated[str, Field(title="Preference key")]
    project_name: Annotated[
        str | None,
        Field(title="Project name", description="None for global preferences"),
    ] = None
    data: Annotated[dict[str, Any], Field(title="Preference data")]
    updated_at: Annotated[datetime, Field(title="Updated at")]


class PreferenceListModel(OPModel):
    preferences: Annotated[list[PreferenceModel], Field(title="Preferences")]


def row_to_model(row: dict[str, Any]) -> PreferenceModel:
    return PreferenceModel(
        key=row["key"],
        project_name=row["project_name"],
        data=row["data"],
        updated_at=row["updated_at"],
    )


async def save_preference(
    user: CurrentUser,
    key: str,
    project_name: str | None,
    data: dict[str, Any],
    *,
    merge: bool,
) -> None:
    """Create the preference, or replace / shallow-merge its data"""

    if project_name:
        await user.ensure_project_access(project_name)

    new_data = "user_preferences.data || EXCLUDED.data" if merge else "EXCLUDED.data"
    query = f"""
        INSERT INTO public.user_preferences (user_name, project_name, key, data)
        VALUES ($1, $2, $3, $4)
        ON CONFLICT (user_name, key, (COALESCE(project_name, '')))
        DO UPDATE SET data = {new_data}, updated_at = NOW()
        RETURNING octet_length(data::text) AS size
    """

    # Size is checked on the stored value (that includes merged data)
    # and the transaction is rolled back when it exceeds the limit.
    try:
        async with Postgres.transaction():
            res = await Postgres.fetchrow(query, user.name, project_name, key, data)
            if res["size"] > MAX_PREFERENCE_SIZE:
                raise BadRequestException(
                    f"Preference data exceeds the limit of {MAX_PREFERENCE_SIZE} bytes"
                )
    except Postgres.ForeignKeyViolationError:
        raise NotFoundException(f"Project {project_name} not found")


@router.get("")
async def list_preferences(
    user: CurrentUser,
    project_name: QProjectName = None,
    key_prefix: Annotated[
        str | None,
        Query(title="Key prefix", examples=["io.ynput.core."]),
    ] = None,
) -> PreferenceListModel:
    """List preferences of the current user in the given scope."""

    conditions = ["user_name = $1", "COALESCE(project_name, '') = COALESCE($2, '')"]
    args: list[Any] = [user.name, project_name]
    if key_prefix:
        args.append(key_prefix)
        conditions.append(f"starts_with(key, ${len(args)})")

    query = f"""
        SELECT key, project_name, data, updated_at
        FROM public.user_preferences
        WHERE {" AND ".join(conditions)}
        ORDER BY key
    """
    preferences = [row_to_model(row) async for row in Postgres.iterate(query, *args)]
    return PreferenceListModel(preferences=preferences)


@router.get("/{key}")
async def get_preference(
    user: CurrentUser,
    key: PPreferenceKey,
    project_name: QProjectName = None,
) -> PreferenceModel:
    """Get a single preference of the current user."""

    res = await Postgres.fetchrow(
        """
        SELECT key, project_name, data, updated_at
        FROM public.user_preferences
        WHERE user_name = $1 AND key = $2
        AND COALESCE(project_name, '') = COALESCE($3, '')
        """,
        user.name,
        key,
        project_name,
    )
    if res is None:
        raise NotFoundException(f"Preference {key} not found")
    return row_to_model(res)


@router.put("/{key}", status_code=204)
async def set_preference(
    user: CurrentUser,
    key: PPreferenceKey,
    data: PreferenceData,
    project_name: QProjectName = None,
) -> EmptyResponse:
    """Create a preference of the current user or replace its data."""

    await save_preference(user, key, project_name, data, merge=False)
    return EmptyResponse()


@router.patch("/{key}", status_code=204)
async def update_preference(
    user: CurrentUser,
    key: PPreferenceKey,
    data: PreferenceData,
    project_name: QProjectName = None,
) -> EmptyResponse:
    """Shallow-merge the data into a preference of the current user.

    Top-level keys of the request body replace the existing ones.
    The preference is created if it does not exist.
    """

    await save_preference(user, key, project_name, data, merge=True)
    return EmptyResponse()


@router.delete("/{key}", status_code=204)
async def delete_preference(
    user: CurrentUser,
    key: PPreferenceKey,
    project_name: QProjectName = None,
) -> EmptyResponse:
    """Delete a preference of the current user."""

    res = await Postgres.fetchrow(
        """
        DELETE FROM public.user_preferences
        WHERE user_name = $1 AND key = $2
        AND COALESCE(project_name, '') = COALESCE($3, '')
        RETURNING key
        """,
        user.name,
        key,
        project_name,
    )
    if res is None:
        raise NotFoundException(f"Preference {key} not found")
    return EmptyResponse()
