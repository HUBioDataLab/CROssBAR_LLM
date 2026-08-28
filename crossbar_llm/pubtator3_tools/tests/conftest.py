"""Shared pytest fixtures for the PubTator3 test suite."""
import json
from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def pytest_configure(config):
    """Reassert pytest-asyncio's auto mode, which this suite requires.

    `asyncio_mode = auto` lives in this directory's pytest.ini, but pytest only
    honours that file when the suite is the sole command-line argument. Name it
    alongside another directory and their common ancestor wins instead, leaving
    every async test here in strict mode and unmarked, so all of them error.
    Setting it here keeps the requirement with the package rather than with how
    pytest happened to be invoked.
    """
    if config.getoption("asyncio_mode", None) != "auto":
        config.option.asyncio_mode = "auto"


@pytest.fixture
def fx():
    """Load any JSON fixture by stem name.

    Usage:
        def test_foo(fx):
            data = fx("pubtator3_relations_example")
    """
    def _load(name: str):
        path = FIXTURES_DIR / f"{name}.json"
        return json.loads(path.read_text())

    return _load
