__all__ = ["app_meta", "tags_meta", "__version__"]

from typing import Any

from ayon_server.version import __version__

app_meta: dict[str, Any] = {
    "title": "Ayon server",
    "description": "Open VFX and Animation pipeline server",
    "version": __version__,
    "contact": {
        "name": "Ynput",
        "email": "info@ynput.io",
        "url": "https://ynput.io",
    },
    "license_info": {
        "name": "Apache License 2.0",
        "url": "http://www.apache.org/licenses/",
    },
    "terms_of_service": "https://ynput.io/terms-of-service",
}


tags_meta: list[dict[str, Any]] = [
    {
        "name": "Authentication",
        "description": """
Authentication endpoints. Most of the endpoints require authentication.

There are two methods of authentication:

- Clients, such as the web interface or Ayon launcher use
  `Authorization` header with `Bearer <token>` value.
  Token is obtained by calling the `/auth/login` endpoint.
  When not in use, the token expires after one day.
- Services use x-api-key header with the API key value.
  API key is generated in the user settings and can be revoked at any time.

Services can additionally use `x-as-user` header to impersonate another user.
This is useful for services that need to create data on behalf of another user.
""",
    },
    {
        "name": "Projects",
        "description": """
Project is a collection of folders and other entities.
Each project has a unique name, which is used as its identifier.

To address an entity within the project, you need to provide
both the project name and the entity ID.
        """,
    },
    {
        "name": "Folders",
        "description": """
Endpoints for managing folders.
        """,
    },
    {
        "name": "Attributes",
        "description": """
Endpoints related to attribute configuration.

Warning: data does not reflect the active configuration of the attributes.
The server needs to be restarted in order the changes become active.
        """,
    },
    {
        "name": "Addon settings",
        "description": """
Addon configuration, site and project overrides...
        """,
    },
    {
        "name": "Secrets",
        "description": """
Sensitive information, like passwords or API keys, can be securely stored in secrets,
which are only accessible by administrators and services.
This makes them an ideal location for storing this type of data.

For addons needing access to secrets, using the 'secret name' in settings
instead of the actual value is recommended.
Consequently, updating secrets won't require any changes to the addon configuration.
""",
    },
]
