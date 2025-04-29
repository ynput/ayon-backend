import httpx

from ayon_server.api.dependencies import CurrentUser
from ayon_server.config import ayonconfig
from ayon_server.entities.user import UserEntity
from ayon_server.exceptions import (
    AyonException,
    ForbiddenException,
    ServiceUnavailableException,
)
from ayon_server.helpers.cloud import (
    CloudUtils,
)
from ayon_server.lib.redis import Redis
from ayon_server.types import OPModel

from .router import router


class UserCustomFields(OPModel):
    level: str = "user"
    instance_id: str | None = None
    verified_user: str | None = None


class CompanyInfo(OPModel):
    id: str
    name: str
    subscriptions: str | None = None


class UserVerificationResponse(OPModel):
    organization: str = "ayon"
    name: str
    email: str | None
    user_id: str
    user_hash: str
    profile_picture: str | None = None
    custom_fields: UserCustomFields
    companies: list[CompanyInfo]


async def get_companies() -> list[CompanyInfo]:
    cinfo = await CloudUtils.get_cloud_info()
    subs = [sub.name for sub in cinfo.subscriptions]

    companies = [
        CompanyInfo(
            id=cinfo.org_id,
            name=cinfo.org_title,
            subscriptions=", ".join(subs) or None,
        ),
    ]
    return companies


async def _get_feedback_verification(
    user: UserEntity, headers: dict[str, str]
) -> UserVerificationResponse:
    if data := await Redis.get_json("feedback-verification", user.name):
        if data.get("status") == "error":
            raise ServiceUnavailableException(
                f"Failed to load feedback token: {data['detail']}"
            )
        return UserVerificationResponse(**data)
    res = None
    payload = {
        "name": user.attrib.fullName or user.name,
        "email": user.attrib.email,
        "avatarUrl": user.attrib.avatarUrl,
    }

    try:
        url = f"{ayonconfig.ynput_cloud_api_url}/api/v2/feedback"
        async with httpx.AsyncClient(headers=headers) as client:
            res = await client.post(url, json=payload)
            res.raise_for_status()
            data = UserVerificationResponse(
                **res.json(),
                companies=await get_companies(),
            )
            await Redis.set_json(
                "feedback-verification",
                user.name,
                data.dict(),
                ttl=7200,
            )
            return data
    except Exception as e:
        if res is not None:
            try:
                detail = res.json()["detail"]
            except Exception:
                detail = res.text[:100]
        else:
            detail = str(e)
        await Redis.set_json(
            "feedback-verification",
            user.name,
            {"status": "error", "detail": detail},
            ttl=600,
        )
        raise AyonException(f"Failed to generate feedback token: {detail}")


@router.get("/feedback")
async def get_feedback_verification(user: CurrentUser) -> UserVerificationResponse:
    """Generate a feedback token for the user"""
    level = "user"
    if user.is_guest:
        raise ForbiddenException("Guest users cannot generate feedback tokens")
    elif user.is_admin:
        level = "admin"
    elif user.is_manager:
        level = "manager"

    # Get headers here to abort if not connected to the cloud
    headers = await CloudUtils.get_api_headers()

    res = await _get_feedback_verification(user, headers)
    res.custom_fields.level = level
    return res
