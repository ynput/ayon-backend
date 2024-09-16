import aiocache
import httpx
from fastapi.responses import RedirectResponse

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

    async with httpx.AsyncClient() as client:
        response = await client.post(
            "http://192.168.5.141:8500/sign",
            json=payload,
            headers=headers,
        )
        if response.status_code > 400:
            print("Error", response.status_code)
            print("Error", response.text)
            return ""

        data = response.json()
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
