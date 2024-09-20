import aiocache
import httpx
from fastapi.responses import RedirectResponse
from nxtools import logging

from ayon_server.config import ayonconfig
from ayon_server.exceptions import ForbiddenException, NotFoundException
from ayon_server.helpers.cloud import get_cloud_api_headers


@aiocache.cached()
async def file_cdn_enabled() -> bool:
    return True


async def get_cdn_link(project_name: str, file_id: str) -> RedirectResponse:
    print("get_cdn_link")
    # Create the payload with project_name, file_id, and an expiration time
    payload = {
        "projectName": project_name,
        "fileId": file_id,
    }

    headers = await get_cloud_api_headers()

    async with httpx.AsyncClient(timeout=ayonconfig.http_timeout) as client:
        res = await client.post(
            f"{ayonconfig.ynput_cloud_api_url}/api/v1/cdn",
            json=payload,
            headers=headers,
        )

    if res.status_code == 401:
        raise ForbiddenException("Unauthorized instance")

    if res.status_code >= 400:
        logging.error("CDN Error", res.status_code)
        logging.error("CDN Error", res.text)
        raise NotFoundException(f"Error {res.status_code} from CDN")

    data = res.json()
    url = data["url"]
    cookies = data.get("cookies", {})

    response = RedirectResponse(url=url, status_code=302)
    for key, value in cookies.items():
        response.set_cookie(
            key,
            value,
            httponly=True,
            secure=True,
            samesite="none",
        )

    return response
