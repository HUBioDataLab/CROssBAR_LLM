from typing import Literal

from pydantic_settings import (
    BaseSettings,
    SettingsConfigDict
)
from pydantic import BaseModel, Field, SecretStr

from crossbar_llm.agent_tools.config import ConfigPaths


class EnvSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ConfigPaths.ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )
    app_env: Literal["development", "production"] = Field(default="development", alias="APP_ENV")
    browser_cookie_secret: SecretStr = Field(alias="BROWSER_COOKIE_SECRET")
    rate_limit_ip_hash_secret: SecretStr = Field(alias="RATE_LIMIT_IP_HASH_SECRET")


class Settings(BaseModel):
    # Env
    env_settings: EnvSettings = Field(default_factory=EnvSettings)

    # App
    app_name: str = "CROSSBAR-LLM Agent API"
    debug: bool = False

    # Rate limiting
    rate_limit_enabled: bool = Field(
        default=True,
        description="If enabled, rate limiting is applied to API requests."
    )

    minute_limit: int = Field(
        default=6,
        description="Maximum number of requests allowed per minute per IP address."
    )

    hour_limit: int = Field(
        default=20,
        description="Maximum number of requests allowed per hour per IP address."
    )

    daily_limit: int = Field(
        default=60,
        description="Maximum number of requests allowed per day per IP address."
    )

    # Sessions
    session_ttl_minutes: int = Field(
        default=45,
        description="Time-to-live for chat sessions in minutes. Sessions older than this will be cleaned up."
    )
    max_sessions_per_user: int = Field(
        default=5,
        description="Maximum number of concurrent sessions allowed per user. If exceeded, the oldest session will be removed."
    )

    # Browser cookie settings
    browser_cookie_name: str = "browser_id"
    browser_cookie_secure: bool = Field(
        default=True,
        description="Whether the browser cookie should be marked as secure (HTTPS only)."
    )
    browser_cookie_samesite: Literal["strict", "lax", "none"] = Field(
        default="lax",
        description="""
        SameSite attribute for the browser cookie. Options: 'strict', 'lax', 'none'.
        - 'strict': Browser sends the cookie only when the user is already on your own site.
        - 'lax': Browser sends the cookie when the user is navigating to your site from an external site (e.g., clicking a link).
        - 'none': Browser sends the cookie in all contexts, including cross-origin requests. Requires Secure to be True.
        """
    )
    browser_cookie_max_age_days: int = Field(
        default=1,
        description="Maximum age of the browser cookie in days. This parameter is only used calculate the max age in seconds for the cookie."
    )

    # Vector search upload
    allowed_upload_extensions: tuple[str, ...] = Field(
        default=("csv", "npy"),
        description="Allowed file extensions for vector search uploads."
    )
    allowed_upload_content_types: tuple[str, ...] = Field(
        default=(
            "text/csv",
            "application/csv",
            "application/vnd.ms-excel",
            "application/octet-stream",
            "application/x-npy",
        ),
        description="Allowed MIME types for vector search uploads.",
    )

    max_upload_size_mb: int = 5

    # CORS
    allowed_origins: list[str] = Field(
        default=[
            "http://localhost:3000",
            "http://127.0.0.1:3000",
        ],
        description="List of allowed origins for CORS. Only used in development mode."
    )
    allowed_credentials: bool = Field(
        default=True,
        description="Whether to allow credentials (cookies, authorization headers, etc.) in CORS requests. Only used in development mode."
    )

    allowed_methods: list[str] = Field(
        default=["*"],
        description="List of allowed HTTP methods for CORS. Only used in development mode."
    )

    allowed_headers: list[str] = Field(
        default=["*"],
        description="List of allowed HTTP headers for CORS. Only used in development mode."
    )


    @property
    def is_dev(self) -> bool:
        return self.env_settings.app_env == "development"
    
    @property
    def upload_size_max_bytes(self) -> int:
        return self.max_upload_size_mb * 1024 * 1024
    
    @property
    def browser_cookie_max_age_seconds(self) -> int:
        return self.browser_cookie_max_age_days * 24 * 60 * 60
    
    def get_rate_limit_settings(self) -> tuple[str, str, str]:
        return reversed((f"{self.minute_limit}/minute", f"{self.hour_limit}/hour", f"{self.daily_limit}/day"))




    



