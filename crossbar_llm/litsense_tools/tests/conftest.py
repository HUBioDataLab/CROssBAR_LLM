"""Shared test helpers. Unit tests read captured responses and never touch the network."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> Any:
    """Load a captured API response by file name."""
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def sentence_fixtures() -> list[Path]:
    return sorted(FIXTURES.glob("sentences_*.json"))


def publication_fixtures() -> list[Path]:
    """Publication fixtures that are documents, excluding the captured error payloads."""
    paths = []
    for path in sorted(FIXTURES.glob("publication_*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, dict) and "passages" in payload:
            paths.append(path)
    return paths
