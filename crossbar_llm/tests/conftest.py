"""Shared setup for the API-level tests.

`Settings`/`EnvSettings` are instantiated at import time (module-level defaults
in `session_store` and `agent_service`), so the required secrets must exist in
the environment before any test module is imported. pytest imports conftest
first, which makes this the only reliable place to put them — doing it at the
top of individual test modules works only for whichever module happens to be
imported first.

These are throwaway values for cookie signing and IP hashing; nothing here
talks to a real service.
"""
import os

import pytest

os.environ.setdefault("BROWSER_COOKIE_SECRET", "test-browser-secret")
os.environ.setdefault("RATE_LIMIT_IP_HASH_SECRET", "test-rate-limit-secret")


@pytest.fixture(autouse=True)
def _paperclip_looks_unconfigured(monkeypatch):
    """Hide any real Paperclip credentials from tests in this directory.

    Scoped to a fixture rather than done at import: clearing these at module
    level would strip them from the whole process, and a combined run
    (`pytest crossbar_llm/`) would then silently skip the Paperclip live suite,
    which gates itself on exactly this variable.
    """
    monkeypatch.delenv("PAPERCLIP_API_KEY", raising=False)
    monkeypatch.delenv("PAPERCLIP_DISABLE_REST", raising=False)
