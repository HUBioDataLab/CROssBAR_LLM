from typing import Literal

from pydantic_settings import (
    BaseSettings,
    SettingsConfigDict
)
from pydantic import BaseModel, Field, SecretStr, field_validator

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
    paperclip_api_key: SecretStr | None = Field(
        default=None,
        alias="PAPERCLIP_API_KEY",
    )
    # Typed as a real bool so `PAPERCLIP_DISABLE_REST=false` means false. The
    # adapter's own env fallback is a bare truthiness check, where that same
    # value would *enable* the flag; parsing it here is what makes the setting
    # behave the way anyone would read it.
    paperclip_disable_rest: bool | None = Field(
        default=None,
        alias="PAPERCLIP_DISABLE_REST",
    )

    @field_validator("paperclip_api_key", "paperclip_disable_rest", mode="before")
    @classmethod
    def _blank_is_unset(cls, value):
        """Treat `KEY=` in a .env as "not configured" rather than as a value.

        `.env.example` ships these keys empty, so a verbatim copy must start
        cleanly — without this, the empty string fails bool parsing and takes
        the whole app down at import.
        """
        if isinstance(value, str) and not value.strip():
            return None
        return value


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

    # Optional literature agents
    literature_tool_timeout_seconds: float = Field(
        default=180.0,
        gt=0,
        description="Maximum runtime for each optional literature tool.",
    )
    literature_max_citations: int = Field(
        default=10,
        ge=1,
        description="Maximum citations returned per literature tool.",
    )
    # Admission limits are per tool because the two tools are bottlenecked by
    # different things, and a single shared pool let one tool's users take
    # capacity from the other's for no benefit. `None` means no local limit.
    paperclip_max_concurrent_runs: int | None = Field(
        default=20,
        ge=1,
        description=(
            "Paperclip runs allowed in flight in this process. The HTTP "
            "connection pool separately caps simultaneous upstream commands; "
            "this limit bounds the number of active agent graphs and LLM calls."
        ),
    )
    pubtator3_max_concurrent_runs: int | None = Field(
        default=50,
        ge=1,
        description=(
            "PubTator3 runs allowed in flight at once in this process. This is "
            "NOT what protects NCBI — the client's rate limiter already holds "
            "every request to NCBI's IP-wide 3 req/s. It bounds latency. A run "
            "makes 2.2 NCBI requests on average (measured over 245 benchmark "
            "questions), so 50 concurrent runs queue for ~36 s on the limiter; "
            "with the ~16-21 s a question spends on LLM calls, the slowest "
            "finishes inside 60 s. Without a cap, a large burst would make "
            "EVERY run slow enough to time out, instead of serving most "
            "promptly and skipping the excess."
        ),
    )
    paperclip_max_pending_runs: int = Field(
        default=40,
        ge=0,
        description="Maximum Paperclip runs waiting for admission in this process.",
    )
    pubtator3_max_pending_runs: int = Field(
        default=50,
        ge=0,
        description="Maximum PubTator3 runs waiting for admission in this process.",
    )
    # Each user's share of a tool's capacity. One run makes one Paperclip
    # search at a time, so this also caps a user's share of Paperclip's
    # per-user search queue. `None` disables the share for that tool.
    paperclip_max_runs_per_user: int | None = Field(
        default=3,
        ge=1,
        description=(
            "Paperclip runs one user may have in flight at once. Without it, "
            "one person firing several questions can occupy most of the "
            "account's search capacity while everyone else waits. Users are "
            "told by the browser cookie, falling back to the hashed client IP."
        ),
    )
    pubtator3_max_runs_per_user: int | None = Field(
        default=3,
        ge=1,
        description=(
            "PubTator3 runs one user may have in flight at once, so one person "
            "cannot take most of NCBI's 3 req/s from everyone else."
        ),
    )
    literature_admission_wait_seconds: float = Field(
        default=30.0,
        ge=0,
        description=(
            "How long a run may queue for an admission slot before it is "
            "reported as skipped. This wait happens BEFORE the per-tool timeout "
            "starts, so it never shortens a run's budget; what it costs is "
            "response time for the queued user. Long enough that a burst "
            "queues briefly instead of being turned away."
        ),
    )
    pubtator3_replica_count: int = Field(
        default=1,
        ge=1,
        description=(
            "Number of API replicas sharing one egress IP. PubTator3's 3 req/s "
            "ceiling is enforced per IP, so each replica takes a 1/N share. "
            "Leave at 1 for a single instance; raise it when scaling out, or "
            "replace the limiter with a coordinated one."
        ),
    )
    paperclip_max_documents: int = Field(
        default=7,
        ge=1,
        description="Papers Paperclip retrieves per question.",
    )
    paperclip_abstracts_only: bool = Field(
        default=True,
        description=(
            "Force Paperclip to title+abstract retrieval. Cheaper and more "
            "predictable in tokens than pulling full bodies."
        ),
    )
    paperclip_use_map: bool = Field(
        default=False,
        description=(
            "Let Paperclip read full text server-side and extract a per-paper "
            "answer. Off by default: it costs one upstream call PER PAPER, so "
            "it multiplies our request rate against a metered service by "
            "`paperclip_max_documents`. Turn on only with headroom to spare."
        ),
    )
    paperclip_max_connections: int = Field(
        default=10,
        ge=1,
        description=(
            "Connections in the shared Paperclip pool, and therefore the most "
            "Paperclip commands this process runs at once. Paperclip documents "
            "10 short commands in flight per account. Tested live on "
            "2026-09-22: metadata reads were not limited even at 30 at once, "
            "but searches share an undocumented per-user queue; 10 searches at "
            "once all succeeded, while 15 drew 429s ('search queue is full'). "
            "So 10 is what keeps concurrent searches safe. The limits are per "
            "account: with N replicas on one API key, set this to about 10 / N, "
            "and leave headroom if benchmarks use the same key."
        ),
    )
    paperclip_pool_timeout_seconds: float = Field(
        default=60.0,
        gt=0,
        description=(
            "How long a Paperclip command may queue for one of those "
            "connections. With the pool sized to the account limit, this IS "
            "the queue: a burst waits here instead of being sent to Paperclip "
            "and rejected. Sized to the 60 s response target; still bounded "
            "by `literature_tool_timeout_seconds` overall."
        ),
    )
    paperclip_max_429_retries: int = Field(
        default=2,
        ge=0,
        description=(
            "Retries for a Paperclip command rejected with 429. Paperclip "
            "answers a full per-user search queue with 429 and Retry-After: 15 "
            "(observed live), and its docs say to wait and retry; without a "
            "retry, that user loses their whole Paperclip answer. 429s on "
            "map/verify are never retried: they mean the daily cap is spent."
        ),
    )
    paperclip_max_retry_wait_seconds: float = Field(
        default=30.0,
        gt=0,
        description=(
            "Longest Retry-After we will honour. If Paperclip asks for a longer "
            "wait, the command fails at once instead of holding a user's "
            "request open that long."
        ),
    )
    pubtator3_max_documents: int = Field(
        default=7,
        ge=1,
        description="Papers PubTator3 exports per question.",
    )
    pubtator3_abstracts_only: bool = Field(
        default=True,
        description=(
            "Force PubTator3 to title+abstract retrieval. On by default: full "
            "text also short-circuits the depth-refinement second pass, and "
            "PubTator3's 3 req/s ceiling is IP-wide, so fewer and smaller "
            "fetches per question is what keeps the service usable under load."
        ),
    )

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




    
