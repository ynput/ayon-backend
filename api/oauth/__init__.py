__all__ = ["router"]

from pydantic import BaseModel
from nxtools import logging

from openpype.lib.postgres import Postgres
from openpype.entities import UserEntity
from openpype.auth import Session
from openpype.config import pypeconfig
from openpype.api import APIException
from yaoauth2 import YAOAuth2, OAuth2Data


class LoginResponseModel(BaseModel):
    detail: str = "Logged in as NAME"
    token: str = "ACCESS_TOKEN"
    user: UserEntity.model()


async def login_callback(data: OAuth2Data) -> LoginResponseModel:
    res = await Postgres.fetch(
        """
        SELECT * FROM public.users WHERE attrib->>'email' = $1
        """,
        data.user.email,
    )
    if not res:
        raise APIException(
            401, f"User with email {data.user.email} was not found."
        )

    user = UserEntity.from_record(**dict(res[0]))

    # User is authorized, so we may revoke the token again
    # In the future, we may want to store the token in the session
    # and revoke it only when the user logs out.

    if not await oauth2.revoke_token(data.provider, data.access_token):
        logging.warning("Unable to revoke oauth token.")

    session = await Session.create(user)
    return LoginResponseModel(
        detail=f"Logged in as {user.name}",
        token=session.token,
        user=session.user
    )

#
# Configure OAuth2 providers
#

oauth2 = YAOAuth2()
oauth2.config.login_callback = login_callback
oauth2.config.login_response_model = LoginResponseModel
oauth2.config.enable_redirect_endpoint = False


if pypeconfig.discord_client_id:
    oauth2.add_provider(
        name="discord",
        client_id=pypeconfig.discord_client_id,
        client_secret=pypeconfig.discord_client_secret
    )

if pypeconfig.google_client_id:
    oauth2.add_provider(
        name="google",
        client_id=pypeconfig.google_client_id,
        client_secret=pypeconfig.google_client_secret
    )

#
# Create router
#

router = oauth2.create_router(
    tags=["Authentication"],
    prefix="/oauth2"
)
