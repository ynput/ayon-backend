"""Server configuration object"""

import os

from pydantic import BaseModel, Field


class AyonConfig(BaseModel):
    """Server configuration"""

    http_listen_address: str = Field(
        default="0.0.0.0",
        description="An address the API server listens on",
    )

    http_listen_port: int = Field(
        default=5000,
        description="A port the API server listens on",
    )

    api_modules_dir: str = Field(
        default="api",
        description="Path to the directory containing the API modules.",
    )

    addons_dir: str = Field(
        default="/addons",
        description="Path to the directory containing the addons.",
    )

    frontend_dir: str = Field(
        default="/frontend",
        description="Path to the directory containing the frontend files.",
    )

    auth_pass_pepper: str = Field(
        default="supersecretpasswordpepper",
        description="A secret string used to salt the password hash.",
    )

    auth_pass_min_length: int = Field(
        default=8,
        description="Minimum password length.",
    )

    auth_pass_complex: str = Field(
        default=True,
        description="Enforce using a complex password.",
    )

    redis_url: str = Field(
        default="redis://redis/",
        description="Connection string for Redis.",
        example="redis://user:password123@redis.example.com:6379",
    )

    redis_channel: str = Field(
        default="pype:c",
        description="Redis channel name for system messages",
    )

    postgres_url: str = Field(
        default="postgres://pypeusr:pypepass@postgres/pype",
        description="Connection string for Postgres.",
        example="postgres://user:password123@postgres.example.com:5432/ayon",
    )

    discord_client_id: str | None = Field(
        default=None,
        description="Discord client ID (for OAuth)",
        example="123456789012345678",
    )

    discord_client_secret: str | None = Field(
        default=None,
        description="Discord client secret (for OAuth)",
        example="123456789012345678",
    )

    google_client_id: str | None = Field(
        default=None,
        description="Google client ID (for OAuth).",
        example="123456789012345678",
    )

    google_client_secret: str | None = Field(
        default=None,
        description="Google client secret (for OAuth)",
        example="123456789012345678",
    )

    motd: str | None = Field(
        default=None,
        description="Message of the day",
        example="Welcome to Ayon!",
    )

    geoip_db_path: str = Field(
        default="/storage/GeoLite2-City.mmdb",
        description="Path to the GeoIP database",
    )


#
# Load configuration from environment variables
#


def load_config() -> AyonConfig:
    """Load configuration"""
    prefix = "ayon_"
    env_data = {}
    for key, value in dict(os.environ).items():
        if not key.lower().startswith(prefix):
            continue

        key = key.lower().removeprefix(prefix)
        if key in AyonConfig.__fields__:
            env_data[key] = value

    return AyonConfig(**env_data)


ayonconfig = load_config()
