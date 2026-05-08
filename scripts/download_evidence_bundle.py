"""Download, verify, and extract a trusted public evidence bundle."""

from __future__ import annotations

import hashlib
import os
import shutil
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath

EVIDENCE_BUNDLE_ENV = "LONGEVITY_LAB_EVIDENCE_BUNDLE"
EVIDENCE_BUNDLE_URL_ENV = "LONGEVITY_LAB_EVIDENCE_BUNDLE_URL"
EVIDENCE_BUNDLE_SHA256_ENV = "LONGEVITY_LAB_EVIDENCE_BUNDLE_SHA256"
ARTIFACTS_DIR_ENV = "LONGEVITY_LAB_ARTIFACTS_DIR"


class EvidenceDownloadError(RuntimeError):
    """Raised when a configured evidence bundle cannot be safely installed."""


def main() -> int:
    """Download and install a configured evidence bundle, or skip when unconfigured."""
    bundle_url = os.getenv(EVIDENCE_BUNDLE_URL_ENV, "").strip()
    expected_sha256 = _normalize_sha256(os.getenv(EVIDENCE_BUNDLE_SHA256_ENV, "").strip())
    bundle_id = os.getenv(EVIDENCE_BUNDLE_ENV, "").strip()
    artifacts_dir = Path(os.getenv(ARTIFACTS_DIR_ENV, "artifacts"))

    if not bundle_url and not expected_sha256 and not bundle_id:
        print("No evidence bundle configured; skipping evidence download.")
        return 0
    if not bundle_url or not expected_sha256 or not bundle_id:
        raise EvidenceDownloadError(
            f"{EVIDENCE_BUNDLE_ENV}, {EVIDENCE_BUNDLE_URL_ENV}, and "
            f"{EVIDENCE_BUNDLE_SHA256_ENV} are required together."
        )

    _validate_bundle_id(bundle_id)
    evidence_dir = artifacts_dir / "evidence"
    with tempfile.TemporaryDirectory(prefix="longevity-evidence-") as temp_dir:
        archive_path = Path(temp_dir) / "evidence.zip"
        _download(bundle_url, archive_path)
        actual_sha256 = _sha256_file(archive_path)
        if actual_sha256 != expected_sha256:
            raise EvidenceDownloadError(
                f"Evidence checksum mismatch: expected {expected_sha256}, got {actual_sha256}."
            )
        _extract_zip(archive_path=archive_path, evidence_dir=evidence_dir, bundle_id=bundle_id)

    print(f"Installed public evidence bundle: {bundle_id}")
    return 0


def _normalize_sha256(value: str) -> str:
    return value.lower().removeprefix("sha256:")


def _download(url: str, destination: Path) -> None:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "longevity-lab-evidence-downloader/1.0"},
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        with destination.open("wb") as output:
            shutil.copyfileobj(response, output)


def _extract_zip(*, archive_path: Path, evidence_dir: Path, bundle_id: str) -> None:
    bundle_dir = evidence_dir / bundle_id
    with zipfile.ZipFile(archive_path) as archive:
        _validate_zip_members(archive=archive, bundle_id=bundle_id)
        if bundle_dir.exists():
            shutil.rmtree(bundle_dir)
        evidence_dir.mkdir(parents=True, exist_ok=True)
        archive.extractall(evidence_dir)

    manifest_path = bundle_dir / "manifest.json"
    if not manifest_path.exists():
        raise EvidenceDownloadError(
            f"Extracted evidence bundle is missing manifest: {manifest_path}"
        )


def _validate_bundle_id(bundle_id: str) -> None:
    path = Path(bundle_id)
    if path.is_absolute() or ".." in path.parts or not bundle_id:
        raise EvidenceDownloadError(f"Unsafe evidence bundle id: {bundle_id!r}")


def _validate_zip_members(*, archive: zipfile.ZipFile, bundle_id: str) -> None:
    for member in archive.infolist():
        filename = member.filename
        path = PurePosixPath(filename)
        if not filename or "\\" in filename or path.is_absolute() or ".." in path.parts:
            raise EvidenceDownloadError(f"Unsafe zip member path: {filename!r}")
        if not path.parts or path.parts[0] != bundle_id:
            raise EvidenceDownloadError(
                f"Zip member {filename!r} is not under expected bundle {bundle_id!r}."
            )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except EvidenceDownloadError as exc:
        print(f"Evidence bundle download failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
