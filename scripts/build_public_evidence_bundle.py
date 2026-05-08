"""Build a public evidence bundle for deployed Community Context surfaces."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import tempfile
import zipfile
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

REQUIRED_FILES = {
    "state_context": Path("processed/context/context_state_year.parquet"),
    "county_context": Path("processed/context/context_county_year.parquet"),
    "places_context": Path("processed/places/places_county_year.parquet"),
}


class EvidenceBundleBuildError(RuntimeError):
    """Raised when a public evidence bundle cannot be built safely."""


def main() -> int:
    """Build a zip archive containing sanitized public evidence assets."""
    args = _parse_args()
    bundle_id = args.bundle_id.strip()
    _validate_bundle_id(bundle_id)
    data_dir = args.data_dir.resolve()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    archive_path = output_dir / f"{bundle_id}.zip"

    with tempfile.TemporaryDirectory(prefix="longevity-evidence-bundle-") as temp_dir:
        bundle_root = Path(temp_dir) / bundle_id
        copied = _copy_evidence_assets(data_dir=data_dir, bundle_root=bundle_root)
        manifest_path = bundle_root / "manifest.json"
        manifest_path.write_text(
            json.dumps(_build_manifest(bundle_id=bundle_id, copied=copied), indent=2) + "\n",
            encoding="utf-8",
        )
        _write_zip(bundle_root=bundle_root, archive_path=archive_path)

    print(f"Built public evidence bundle: {archive_path}")
    print(f"SHA256: {_sha256_file(archive_path)}")
    return 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument("--bundle-id", required=True)
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/evidence/releases"))
    return parser.parse_args()


def _copy_evidence_assets(
    *,
    data_dir: Path,
    bundle_root: Path,
) -> dict[str, list[Path] | Path]:
    copied: dict[str, list[Path] | Path] = {}
    for role, relative_path in REQUIRED_FILES.items():
        source = data_dir / relative_path
        if not source.exists():
            raise EvidenceBundleBuildError(f"Missing required evidence asset: {source}")
        copied[role] = _copy_file(source=source, destination=bundle_root / relative_path)

    validation_paths = sorted((data_dir / "processed" / "validation").glob("*.json"))
    if not validation_paths:
        raise EvidenceBundleBuildError(
            f"Missing required validation JSON files under {data_dir / 'processed' / 'validation'}"
        )
    copied["places_validation"] = [
        _copy_file(
            source=path,
            destination=bundle_root / path.relative_to(data_dir),
        )
        for path in validation_paths
    ]

    causal_root = data_dir / "processed" / "reports" / "causal"
    causal_paths = sorted(causal_root.glob("*/*_report.json")) if causal_root.exists() else []
    report_paths: list[Path] = []
    for report in causal_paths:
        report_paths.append(
            _copy_file(
                source=report,
                destination=bundle_root / report.relative_to(data_dir),
            )
        )
        markdown = report.with_suffix(".md")
        if markdown.exists():
            report_paths.append(
                _copy_file(
                    source=markdown,
                    destination=bundle_root / markdown.relative_to(data_dir),
                )
            )
    copied["causal_reports"] = report_paths
    return copied


def _copy_file(*, source: Path, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    return destination


def _build_manifest(*, bundle_id: str, copied: dict[str, list[Path] | Path]) -> dict[str, object]:
    roles: dict[str, object] = {}
    for role, value in copied.items():
        if isinstance(value, list):
            roles[role] = [
                _file_entry(path) for path in sorted(value, key=lambda item: item.as_posix())
            ]
        else:
            roles[role] = _file_entry(value)
    return {
        "bundle_id": bundle_id,
        "schema_version": "public-evidence-bundle/v1",
        "created_at": datetime.now(UTC).isoformat(),
        "purpose": (
            "Community Context production evidence surfaces only; not used by Explorer scoring."
        ),
        "roles": roles,
    }


def _file_entry(path: Path) -> dict[str, object]:
    relative_path = _bundle_relative_path(path)
    return {
        "path": relative_path,
        "bytes": path.stat().st_size,
        "sha256": _sha256_file(path),
    }


def _bundle_relative_path(path: Path) -> str:
    parts = path.parts
    if "processed" not in parts:
        raise EvidenceBundleBuildError(f"Unexpected bundled path: {path}")
    return Path(*parts[parts.index("processed") :]).as_posix()


def _write_zip(*, bundle_root: Path, archive_path: Path) -> None:
    if archive_path.exists():
        archive_path.unlink()
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(bundle_root.rglob("*")):
            if not path.is_file():
                continue
            relative_name = path.relative_to(bundle_root.parent).as_posix()
            _validate_zip_member(relative_name, bundle_root.name)
            archive.write(path, relative_name)


def _validate_bundle_id(bundle_id: str) -> None:
    path = Path(bundle_id)
    if path.is_absolute() or ".." in path.parts or not bundle_id:
        raise EvidenceBundleBuildError(f"Unsafe evidence bundle id: {bundle_id!r}")


def _validate_zip_member(filename: str, bundle_id: str) -> None:
    path = PurePosixPath(filename)
    if not filename or "\\" in filename or path.is_absolute() or ".." in path.parts:
        raise EvidenceBundleBuildError(f"Unsafe zip member path: {filename!r}")
    if not path.parts or path.parts[0] != bundle_id:
        raise EvidenceBundleBuildError(
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
    except EvidenceBundleBuildError as exc:
        print(f"Evidence bundle build failed: {exc}")
        raise SystemExit(1) from exc
