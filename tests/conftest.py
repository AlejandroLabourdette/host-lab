"""Fixtures shared across the manifest tests."""

from __future__ import annotations

import copy
from collections.abc import Callable
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


@pytest.fixture
def write_generation() -> Callable[..., None]:
    """Write one Valheim save cycle into a world directory.

    Shared rather than duplicated because both the state tests and the backup
    tests need a world shaped the way Valheim shapes one since 1.0: a numbered
    generation of metadata, data and index files, chunk files alongside, and a
    completion marker only once the save finished.
    """

    def write(world: Path, number: int, *, complete: bool = True) -> None:
        world.mkdir(parents=True, exist_ok=True)
        for suffix in ("fwl2", "db2", "chunks"):
            (world / f"_main.{number}.{suffix}").write_text(f"generation {number}")
        (world / "00_00__0_1.chunk").write_text("terrain")
        if complete:
            (world / f"_main.{number}.ok").write_text("")

    return write
