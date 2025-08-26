import asyncio

from ayon_server.auth.tokenauth import TokenPayload
from ayon_server.exceptions import (
    InvalidSettingsException,
)
from ayon_server.helpers.crypto import encrypt_json_urlsafe
from ayon_server.helpers.email import is_mailing_enabled
from ayon_server.helpers.external_users import ExternalUsers
from ayon_server.initialize import ayon_init


async def create_login_link(
    email: str,
    *,
    full_name: str | None = None,
    external: bool = True,
    project_name: str | None = None,
    redirect_url: str | None = None,
) -> None:
    if not await is_mailing_enabled():
        raise InvalidSettingsException(
            "Mailing is not enabled. Please check the server settings."
        )

    payload = TokenPayload(
        email=email,
        full_name=full_name,
        external=external,
        project_name=project_name,
        redirect_url=redirect_url,
    )

    enc_data = await encrypt_json_urlsafe(payload.dict(exclude_none=True))
    token = enc_data.token
    await enc_data.set_nonce()

    login_link = f"http://localhost:3000/login/_token?q={token}"

    print(login_link)


EMAIL = "foo.bar@post.cz"
PROJECT_NAME = "wing_it"
FULL_NAME = "Foo Bar"


async def main():
    await ayon_init(extensions=False)

    if not await ExternalUsers.exists(EMAIL, project_name=PROJECT_NAME):
        print("Adding external user...")

        await ExternalUsers.add(
            email=EMAIL, project_name=PROJECT_NAME, full_name=FULL_NAME
        )

    await create_login_link(
        email=EMAIL,
        full_name=FULL_NAME,
        external=True,
        project_name=PROJECT_NAME,
        redirect_url="http://localhost:3000/projects/wing_it/reviews/72add6e2454911f0a4f30242ac130004",
    )


if __name__ == "__main__":
    asyncio.run(main())
