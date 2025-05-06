__all__ = ["app_meta", "__version__"]

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
        "name": "Functional Source License, Version 1.1",
        "url": "https://github.com/ynput/ayon-backend?tab=License-1-ov-file#readme",
    },
    "terms_of_service": "https://ynput.io/terms-of-service",
}
