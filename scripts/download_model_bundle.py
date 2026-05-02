"""Download, verify, and extract a trusted model artifact bundle.

This script intentionally uses only the Python standard library so it can run
during platform build steps before the package itself is installed.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath

ARTIFACT_URL_ENV = "LONGEVITY_LAB_ARTIFACT_URL"
ARTIFACT_SHA256_ENV = "LONGEVITY_LAB_ARTIFACT_SHA256"
ARTIFACTS_DIR_ENV = "LONGEVITY_LAB_ARTIFACTS_DIR"
ARTIFACT_BUNDLE_ENV = "LONGEVITY_LAB_ARTIFACT_BUNDLE"


class ArtifactDownloadError(RuntimeError):
    """Raised when a configured artifact bundle cannot be safely installed."""


def main() -> int:
    """Download and install a configured artifact bundle, or skip when unconfigured."""
    artifact_url = os.getenv(ARTIFACT_URL_ENV, "").strip()
    expected_sha256 = _normalize_sha256(os.getenv(ARTIFACT_SHA256_ENV, "").strip())
    bundle_id = os.getenv(ARTIFACT_BUNDLE_ENV, "").strip()
    artifacts_dir = Path(os.getenv(ARTIFACTS_DIR_ENV, "artifacts"))

    if not artifact_url and not expected_sha256:
        print("No model artifact URL configured; skipping artifact download.")
        return 0
    if not artifact_url or not expected_sha256:
        raise ArtifactDownloadError(
            f"Both {ARTIFACT_URL_ENV} and {ARTIFACT_SHA256_ENV} are required."
        )
    if not bundle_id:
        raise ArtifactDownloadError(f"{ARTIFACT_BUNDLE_ENV} is required for artifact downloads.")

    _validate_bundle_id(bundle_id)
    models_dir = artifacts_dir / "models"
    with tempfile.TemporaryDirectory(prefix="longevity-artifact-") as temp_dir:
        archive_path = Path(temp_dir) / "bundle.zip"
        _download(artifact_url, archive_path)
        actual_sha256 = _sha256_file(archive_path)
        if actual_sha256 != expected_sha256:
            raise ArtifactDownloadError(
                f"Artifact checksum mismatch: expected {expected_sha256}, got {actual_sha256}."
            )
        _extract_zip(archive_path=archive_path, models_dir=models_dir, bundle_id=bundle_id)

    print(f"Installed model artifact bundle: {bundle_id}")
    return 0


def _normalize_sha256(value: str) -> str:
    """Normalize a SHA256 value with or without a ``sha256:`` prefix."""
    lowered = value.lower()
    return lowered.removeprefix("sha256:")


def _validate_bundle_id(bundle_id: str) -> None:
    """Reject unsafe bundle identifiers before using them as paths."""
    rel = Path(bundle_id)
    if rel.is_absolute() or ".." in rel.parts or not bundle_id:
        raise ArtifactDownloadError(f"Unsafe artifact bundle id: {bundle_id!r}")


def _download(url: str, destination: Path) -> None:
    """Download ``url`` to ``destination`` with a stable user agent."""
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "longevity-lab-artifact-downloader/1.0"},
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        with destination.open("wb") as output:
            shutil.copyfileobj(response, output)


def _sha256_file(path: Path) -> str:
    """Return the lowercase SHA256 hex digest for a file."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _extract_zip(*, archive_path: Path, models_dir: Path, bundle_id: str) -> None:
    """Safely extract a bundle zip under ``models_dir``."""
    bundle_dir = models_dir / bundle_id
    with zipfile.ZipFile(archive_path) as archive:
        _validate_zip_members(archive=archive, bundle_id=bundle_id)
        if bundle_dir.exists():
            shutil.rmtree(bundle_dir)
        models_dir.mkdir(parents=True, exist_ok=True)
        archive.extractall(models_dir)

    manifest_path = bundle_dir / "manifest.json"
    if not manifest_path.exists():
        raise ArtifactDownloadError(f"Extracted bundle is missing manifest: {manifest_path}")


def _validate_zip_members(*, archive: zipfile.ZipFile, bundle_id: str) -> None:
    """Reject zip entries that would escape or pollute the target bundle."""
    for member in archive.infolist():
        filename = member.filename
        if not filename or "\\" in filename:
            raise ArtifactDownloadError(f"Unsafe zip member path: {filename!r}")
        path = PurePosixPath(filename)
        if path.is_absolute() or ".." in path.parts:
            raise ArtifactDownloadError(f"Unsafe zip member path: {filename!r}")
        if path.parts and path.parts[0] != bundle_id:
            raise ArtifactDownloadError(
                f"Zip member {filename!r} is not under expected bundle {bundle_id!r}."
            )


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ArtifactDownloadError as exc:
        print(f"Artifact download failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
