"""Fixtures shared across the manifest tests."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest
import yaml

VALHEIM_MANIFEST = Path("titles/valheim.yaml")


@pytest.fixture
def valheim_raw() -> dict[str, Any]:
    """The real Valheim manifest, as data, so a test can mutate one field.

    Tests that check a refusal start from something valid and break exactly one
    thing. Building a minimal manifest by hand instead would let the fixture
    drift away from the file the platform actually loads, and then the tests
    would be checking a manifest nobody ships.
    """
    loaded = yaml.safe_load(VALHEIM_MANIFEST.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


@pytest.fixture
def write_manifest(tmp_path: Path) -> object:
    """Write a manifest dict to a temporary file and hand back the path."""

    def write(raw: dict[str, Any], name: str = "title.yaml") -> Path:
        path = tmp_path / name
        path.write_text(yaml.safe_dump(copy.deepcopy(raw)), encoding="utf-8")
        return path

    return write
