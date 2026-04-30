"""Tests for artifact bundle discovery and safety checks."""

from __future__ import annotations

from pathlib import Path

import pytest

from longevity_lab.artifacts.manifest import ArtifactManifest, DatasetInfo, save_manifest
from longevity_lab.artifacts.store import ArtifactStore


def test_artifact_store_rejects_bundle_id_path_traversal(tmp_path: Path) -> None:
    """bundle_id should not be able to escape the configured base_dir."""
    base_dir = tmp_path / "models"
    base_dir.mkdir()

    escape_dir = tmp_path / "escape"
    escape_dir.mkdir()
    save_manifest(
        ArtifactManifest(dataset=DatasetInfo(name="brfss", version="test")),
        escape_dir / "manifest.json",
    )

    store = ArtifactStore(base_dir)
    with pytest.raises(ValueError, match="Unsafe bundle_id"):
        store.resolve(bundle_id="../escape")
