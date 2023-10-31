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
        description="Absolute path to the directory containing the addons.",
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
        default="postgres://ayon:ayon@postgres/ayon",
        description="Connection string for Postgres.",
        example="postgres://user:password123@postgres.example.com:5432/ayon",
    )

    session_ttl: int = Field(
        default=24 * 3600,
        description="Session lifetime in seconds",
    )

    max_failed_login_attempts: int = Field(
        default=10,
        description="Maximum number of failed login attempts",
    )

    failed_login_ban_time: int = Field(
        default=600,
        description="Interval in seconds to ban IP addresses with too many failed login attempts",
    )

    motd: str | None = Field(
        default=None,
        description="Message of the day",
        example="Welcome to Ayon!",
    )

    motd_path: str | None = Field(
        default="/storage/motd.md",
        description="Path to the MOTD file",
    )

    login_page_background: str | None = Field(
        default=None,
        description="Login page background image",
        example="https://example.com/background.jpg",
    )

    login_page_brand: str | None = Field(
        default=None,
        description="Login page brand image",
        example="https://example.com/brand.png",
    )

    geoip_db_path: str = Field(
        default="/storage/GeoLite2-City.mmdb",
        description="Path to the GeoIP database",
    )

    force_create_admin: bool = Field(
        default=False,
        description="Ensure creation of admin user on first run",
    )

    disable_rest_docs: bool = Field(
        default=False,
        description="Disable REST API documentation",
    )

    audit_trail: bool = Field(
        default=True,
        description="Enable audit trail",
    )

    ynput_connect_url: str | None = Field(
        "https://connect.ynput.io",
        description="YnputConnect URL",
    )

    http_timeout: int = Field(
        default=120,
        description="Timeout for HTTP requests the server uses "
        "to connect to external services",
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

    config = AyonConfig(**env_data)

    if (config.motd) is None and (config.motd_path is not None):
        if os.path.exists(config.motd_path):
            with open(config.motd_path, "r") as motd_file:
                config.motd = motd_file.read()

    return config


ayonconfig = load_config()
