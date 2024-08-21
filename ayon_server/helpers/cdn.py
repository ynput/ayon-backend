import datetime

import aiocache
import jwt
from fastapi.responses import RedirectResponse


@aiocache.cached()
async def file_cdn_enabled() -> bool:
    return True


def get_cdn_link(project_name: str, file_id: str) -> RedirectResponse:
    secret_key = "5baae0654f538e23c97931427352fb106a76af1efc8c9894acdf48c180006856"

    # Create the payload with project_name, file_id, and an expiration time
    payload = {
        "project_name": project_name,
        "file_id": file_id,
        "exp": datetime.datetime.utcnow()
        + datetime.timedelta(hours=1),  # Token expires in 1 hour
    }
    # Encode the token
    token = jwt.encode(payload, secret_key, algorithm="HS256")
    print(f"Generated JWT: {token}")
    url = f"http://localhost:8080/video?token={token}"

    return RedirectResponse(url=url, status_code=302)
