from fastapi import Request

from ayon_server.api.dependencies import CurrentUser
from ayon_server.api.responses import EmptyResponse
from ayon_server.exceptions import ForbiddenException
from ayon_server.lib.postgres import Postgres

from .router import router


@router.post("/abort")
async def abort_onboarding(request: Request, user: CurrentUser) -> EmptyResponse:
    """Abort the onboarding process (disable nag screen)"""

    if user.is_admin:
        raise ForbiddenException()

    await Postgres().execute(
        """
        INSERT INTO config (key, value)
        VALUES ('onboardingFinished', 'true'::jsonb)
        """
    )

    return EmptyResponse()
