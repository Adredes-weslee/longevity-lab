"""Tests for the build-time model artifact downloader."""

from __future__ import annotations

import hashlib
import importlib.util
import zipfile
from pathlib import Path
from types import ModuleType

import pytest


def _load_downloader() -> ModuleType:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "download_model_bundle.py"
    spec = importlib.util.spec_from_file_location("download_model_bundle", script_path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _write_bundle_zip(path: Path, *, bundle_id: str, unsafe_name: str | None = None) -> str:
    with zipfile.ZipFile(path, "w") as archive:
        if unsafe_name is not None:
            archive.writestr(unsafe_name, "unsafe")
        else:
            archive.writestr(f"{bundle_id}/manifest.json", '{"schema_version": 1}')
            archive.writestr(f"{bundle_id}/heart_disease.joblib", "model")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_download_model_bundle_installs_verified_zip(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A configured file URL should be verified and extracted under artifacts/models."""
    downloader = _load_downloader()
    bundle_id = "bundle-test"
    archive_path = tmp_path / "bundle.zip"
    digest = _write_bundle_zip(archive_path, bundle_id=bundle_id)
    artifacts_dir = tmp_path / "artifacts"

    monkeypatch.setenv("LONGEVITY_LAB_ARTIFACT_URL", archive_path.as_uri())
    monkeypatch.setenv("LONGEVITY_LAB_ARTIFACT_SHA256", digest)
    monkeypatch.setenv("LONGEVITY_LAB_ARTIFACT_BUNDLE", bundle_id)
    monkeypatch.setenv("LONGEVITY_LAB_ARTIFACTS_DIR", str(artifacts_dir))

    assert downloader.main() == 0
    assert (artifacts_dir / "models" / bundle_id / "manifest.json").exists()


def test_download_model_bundle_rejects_checksum_mismatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Checksum mismatches should fail before extraction."""
    downloader = _load_downloader()
    bundle_id = "bundle-test"
    archive_path = tmp_path / "bundle.zip"
    _write_bundle_zip(archive_path, bundle_id=bundle_id)
    artifacts_dir = tmp_path / "artifacts"

    monkeypatch.setenv("LONGEVITY_LAB_ARTIFACT_URL", archive_path.as_uri())
    monkeypatch.setenv("LONGEVITY_LAB_ARTIFACT_SHA256", "0" * 64)
    monkeypatch.setenv("LONGEVITY_LAB_ARTIFACT_BUNDLE", bundle_id)
    monkeypatch.setenv("LONGEVITY_LAB_ARTIFACTS_DIR", str(artifacts_dir))

    with pytest.raises(downloader.ArtifactDownloadError, match="checksum mismatch"):
        downloader.main()
    assert not (artifacts_dir / "models" / bundle_id).exists()


def test_download_model_bundle_rejects_zip_slip(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Zip entries outside the expected bundle directory should be rejected."""
    downloader = _load_downloader()
    bundle_id = "bundle-test"
    archive_path = tmp_path / "bundle.zip"
    digest = _write_bundle_zip(archive_path, bundle_id=bundle_id, unsafe_name="../evil.txt")

    monkeypatch.setenv("LONGEVITY_LAB_ARTIFACT_URL", archive_path.as_uri())
    monkeypatch.setenv("LONGEVITY_LAB_ARTIFACT_SHA256", digest)
    monkeypatch.setenv("LONGEVITY_LAB_ARTIFACT_BUNDLE", bundle_id)
    monkeypatch.setenv("LONGEVITY_LAB_ARTIFACTS_DIR", str(tmp_path / "artifacts"))

    with pytest.raises(downloader.ArtifactDownloadError, match="Unsafe zip member"):
        downloader.main()


def test_download_model_bundle_skips_when_unconfigured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Local builds without artifact env vars should continue unchanged."""
    downloader = _load_downloader()
    monkeypatch.delenv("LONGEVITY_LAB_ARTIFACT_URL", raising=False)
    monkeypatch.delenv("LONGEVITY_LAB_ARTIFACT_SHA256", raising=False)
    monkeypatch.delenv("LONGEVITY_LAB_ARTIFACT_BUNDLE", raising=False)

    assert downloader.main() == 0
