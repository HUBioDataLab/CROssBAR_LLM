import pytest
from fastapi import HTTPException, status
from pydantic import BaseModel, Field

from crossbar_llm.api.core import deps


class _MissingNeo4jSettings(BaseModel):
    user: str = Field(alias="NEO4J_USER")
    password: str = Field(alias="NEO4J_PASSWORD")
    database: str = Field(alias="NEO4J_DB_NAME")


@pytest.fixture
def unconfigured_backend(monkeypatch):
    """Make `AgentService()` fail the way a missing Neo4j config makes it fail."""
    deps.get_runtime_service.cache_clear()
    monkeypatch.setattr(
        deps, "AgentService", lambda: _MissingNeo4jSettings.model_validate({})
    )
    yield
    deps.get_runtime_service.cache_clear()


def _force_env(monkeypatch, *, is_dev: bool):
    """Pin the environment rather than inheriting whatever .env happens to say."""
    monkeypatch.setattr(
        deps, "Settings", lambda: type("S", (), {"is_dev": is_dev})()
    )


def test_missing_configuration_returns_503(unconfigured_backend, monkeypatch):
    _force_env(monkeypatch, is_dev=True)

    with pytest.raises(HTTPException) as caught:
        deps.get_runtime_service()

    assert caught.value.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert "knowledge-graph backend is not configured" in caught.value.detail


def test_development_names_the_missing_variables(unconfigured_backend, monkeypatch):
    _force_env(monkeypatch, is_dev=True)

    with pytest.raises(HTTPException) as caught:
        deps.get_runtime_service()

    detail = caught.value.detail
    assert "NEO4J_USER" in detail
    assert "NEO4J_PASSWORD" in detail
    assert "NEO4J_DB_NAME" in detail


def test_production_withholds_the_variable_names(unconfigured_backend, monkeypatch):
    """The names confirm the backend stack to anyone hitting a misconfigured
    public deployment. They go to the logs instead; the user-facing sentence
    already says everything a caller can act on."""
    _force_env(monkeypatch, is_dev=False)

    with pytest.raises(HTTPException) as caught:
        deps.get_runtime_service()

    detail = caught.value.detail
    assert "knowledge-graph backend is not configured" in detail
    assert "NEO4J" not in detail
    assert "Missing environment variables" not in detail


def test_failure_is_not_cached_so_a_fixed_config_recovers(unconfigured_backend, monkeypatch):
    """`lru_cache` does not memoise exceptions, so construction is retried once
    the environment is corrected — and a failed build leaves the cache empty,
    which is what the shutdown hook checks before calling `aclose`."""
    _force_env(monkeypatch, is_dev=True)

    with pytest.raises(HTTPException):
        deps.get_runtime_service()
    assert deps.get_runtime_service.cache_info().currsize == 0

    sentinel = object()
    monkeypatch.setattr(deps, "AgentService", lambda: sentinel)
    assert deps.get_runtime_service() is sentinel
