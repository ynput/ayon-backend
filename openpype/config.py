"""Server configuration object"""

import os

from pydantic import BaseModel, Field


class PypeConfig(BaseModel):
    """Server configuration"""

    api_modules_dir: str = Field(
        default="api", description="Path to the directory containing the API modules."
    )

    auth_pass_pepper: str = Field(
        default="supersecretpasswordpepper",
        description="A secret string used to salt the password hash.",
    )

    auth_pass_min_length: int = Field(default=8, description="Minimum password length.")

    auth_pass_complex: str = Field(
        default=True, description="Force using a complex password."
    )

    redis_url: str = Field(
        default="redis://redis/", description="Connection string for Redis."
    )

    postgres_url: str = Field(
        default="postgres://pypeusr:pypepass@postgres/pype",
        description="Connection string for Postgres.",
    )

    discord_client_id: str | None = Field(
        default=None, description="Discord client ID."
    )

    discord_client_secret: str | None = Field(
        default=None, description="Discord client secret."
    )

    google_client_id: str | None = Field(default=None, description="Google client ID.")

    google_client_secret: str | None = Field(
        default=None, description="Google client secret."
    )


#
# Load configuration from environment variables
#


def load_config() -> PypeConfig:
    """Load configuration"""
    env_prefix = "openpype_"
    env_data = {}
    for key, value in dict(os.environ).items():
        if not key.lower().startswith(env_prefix):
            continue

        key = key.lower().removeprefix(env_prefix)
        if key in PypeConfig.__fields__:
            env_data[key] = value

    return PypeConfig(**env_data)


pypeconfig = load_config()
