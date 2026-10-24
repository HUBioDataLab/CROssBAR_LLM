"""Application configuration.

Every knob in the system lives here and is overridable by environment variable with the
``LITSENSE_`` prefix. Nothing is hardcoded at a call site.
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration for the LitSense agent."""

    model_config = SettingsConfigDict(
        env_prefix="LITSENSE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Search ------------------------------------------------------------------------
    top_k_sentences: int = Field(
        default=100,
        ge=1,
        le=100,
        description="Sentences requested from the search endpoint. The API maximum is 100.",
    )
    rerank: bool = Field(
        default=True,
        description="Value of the search endpoint's `rerank` flag.",
    )
    min_score: float | None = Field(
        default=None,
        description=(
            "Optional score floor applied in `select`. Stays None by default: score semantics "
            "under rerank=true are not understood, so scores order within a response only "
            "(ADR-001)."
        ),
    )
    low_relevance_score: float | None = Field(
        default=0.6,
        ge=0.0,
        le=1.0,
        description=(
            "When the best scored hit falls below this, the answer carries a low-relevance "
            "warning. Advisory only — nothing is filtered or refused (ADR-007). None "
            "disables it. Meaningless with rerank=False, where no hit is scored."
        ),
    )

    # --- Selection ---------------------------------------------------------------------
    max_articles: int = Field(
        default=10,
        ge=1,
        description="Distinct publications carried into the answer.",
    )
    section: str = Field(
        default="abstract",
        description="Publication section fetched for each selected pmid.",
    )

    # --- Full text / depth refinement (ADR-009) ----------------------------------------
    full_text: bool = Field(
        default=False,
        description=(
            "Allow the depth-refinement loop: after synthesis an LLM judges the answer's "
            "scientific depth, and an insufficient verdict re-fetches BioC-PMC full text "
            "for the evidence articles and synthesizes once more. Default off — answers "
            "come from abstracts unless the user says otherwise (Trello, 2026-08-18)."
        ),
    )
    full_text_max_chars: int = Field(
        default=30_000,
        ge=1_000,
        description=(
            "Per-article cap on narrative full-text characters handed to the model. "
            "Observed articles carry ~77K chars total incl. references; the narrative body "
            "is what we keep, and this caps the prompt blow-up the reference harness "
            "warned about."
        ),
    )
    full_text_url: str = Field(
        default=(
            "https://www.ncbi.nlm.nih.gov/research/bionlp/RESTful/pmcoa.cgi/"
            "BioC_json/{pmcid}/unicode"
        ),
        description="BioC-PMC full-text endpoint template; {pmcid} needs the PMC prefix.",
    )

    # --- Relevance gate ----------------------------------------------------------------
    relevance_gate: bool = Field(
        default=True,
        description=(
            "Ask the LLM whether the question is a coherent biomedical question before any "
            "retrieval; a negative verdict ends the pipeline with an explanatory answer "
            "(ADR-008, supervisor-mandated). False removes the gate node entirely."
        ),
    )

    answer_style: str = Field(
        default="prose",
        pattern="^(prose|bare)$",
        description=(
            "Synthesis output style. 'prose' (default): one consolidated paragraph across "
            "articles. 'bare': only the requested items, for benchmark overlap scoring "
            "(Trello evaluation card, 2026-08-18)."
        ),
    )

    # --- LLM ---------------------------------------------------------------------------
    model: str = Field(
        description=(
            "Provider-qualified model string, e.g. 'anthropic:claude-sonnet-4-6'. Required: "
            "the provider is a deployment decision, not a code decision (ADR-004)."
        ),
    )

    reasoning_effort: str | None = Field(
        default=None,
        pattern="^(none|minimal|low|medium|high)$",
        description=(
            "Reasoning/thinking effort requested from the model, for providers that expose "
            "it (OpenRouter's unified `reasoning` parameter; ADR-010). None sends nothing "
            "and leaves the provider default; 'none' asks for reasoning to be switched off "
            "explicitly; the other levels request that effort. Applies to every call the "
            "agent makes (gate, synthesis, depth evaluator)."
        ),
    )

    provider_order: str | None = Field(
        default=None,
        description=(
            "OpenRouter only: comma-separated upstream providers to try first for the "
            "model (e.g. 'Alibaba,DeepInfra'), fallbacks allowed. Open-weight models are "
            "served by many providers of unequal quality — some ignore the JSON-schema "
            "response format or drop reasoning (DeepSeek V4, 2026-09-22) — and this pins "
            "the run to ones that honour both. Whenever any OpenRouter-specific request "
            "field is sent (this or reasoning_effort), `require_parameters` is set too, "
            "so a provider that cannot honour the request is skipped rather than "
            "answering wrongly (ADR-010)."
        ),
    )
    structured_output_method: str | None = Field(
        default=None,
        pattern="^(json_schema|function_calling|json_mode)$",
        description=(
            "How structured output is requested from the model (LangChain's "
            "`with_structured_output(method=...)`). None = LangChain's default for the "
            "provider (JSON schema on OpenAI-compatible endpoints). Some models behind "
            "OpenRouter ignore the JSON-schema response format and answer in prose "
            "(DeepSeek V4, observed 2026-09-22); 'function_calling' routes the same schema "
            "through a tool call, which those models honour (ADR-010)."
        ),
    )

    # --- HTTP client -------------------------------------------------------------------
    http_cache_dir: str | None = Field(
        default=None,
        description=(
            "Directory for an on-disk cache of NCBI responses, shared by every process "
            "pointed at it (ADR-010). None (default) keeps the in-memory per-pmid cache "
            "only. Meant for benchmark runs that replay the same questions: identical "
            "retrieval for every model, and one request to NCBI per URL however many runs "
            "execute in parallel."
        ),
    )
    api_base_url: str = Field(
        default="https://www.ncbi.nlm.nih.gov/research/litsense2-api",
        description="Root of the LitSense 2.0 API.",
    )
    user_agent: str = Field(
        default="litsense-agent/0.1 (research prototype)",
        description="Sent on every request. We are a guest on NCBI infrastructure (ADR-002).",
    )
    request_timeout_s: float = Field(
        default=30.0,
        gt=0,
        description="Per-request timeout. No request is ever unbounded.",
    )
    max_concurrency: int = Field(
        default=1,
        ge=1,
        description=(
            "Concurrent outbound requests, enforced globally by the shared client (ADR-002)."
        ),
    )
    requests_per_second: float = Field(
        default=1.0,
        gt=0,
        description=(
            "Global outbound request rate. The published NCBI limit is roughly 1 req/s; raise "
            "only if that published limit changes."
        ),
    )
    max_retries: int = Field(
        default=3,
        ge=0,
        description="Retry attempts on 429 and 5xx. Other 4xx are never retried (ADR-002).",
    )
    retry_backoff_base_s: float = Field(
        default=1.0,
        gt=0,
        description="Base delay for exponential backoff with jitter.",
    )
