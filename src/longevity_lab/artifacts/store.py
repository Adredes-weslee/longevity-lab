"""Artifact bundle discovery and loading utilities."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from longevity_lab.artifacts.manifest import ArtifactManifest, load_manifest


@dataclass(frozen=True, slots=True)
class ArtifactBundle:
    """A resolved artifact bundle directory plus its manifest."""

    path: Path
    manifest: ArtifactManifest


class ArtifactStore:
    """Locate and load model artifact bundles from a base directory."""

    def __init__(self, base_dir: Path) -> None:
        """Store the base directory containing bundle subfolders."""
        self._base_dir = base_dir

    def list_bundle_dirs(self) -> list[Path]:
        """Return candidate bundle directories under the base dir."""
        if not self._base_dir.exists():
            return []
        return [path for path in self._base_dir.iterdir() if path.is_dir()]

    def bundle_id(self, bundle: ArtifactBundle) -> str:
        """Return the bundle path relative to the artifact-store base directory."""
        base_resolved = self._base_dir.resolve()
        bundle_path = bundle.path.resolve()
        return bundle_path.relative_to(base_resolved).as_posix()

    def resolve(self, bundle_id: str | None = None) -> ArtifactBundle:
        """Resolve an artifact bundle by id or pick the latest available."""
        bundles = self.resolve_all(bundle_id)
        if bundles:
            return bundles[0]
        raise FileNotFoundError(
            "No artifact bundles found. Train a model bundle or set LONGEVITY_LAB_ENGINE=demo."
        )

    def resolve_all(self, bundle_id: str | None = None) -> list[ArtifactBundle]:
        """Resolve candidate artifact bundles by id or newest-first discovery order."""
        if bundle_id:
            rel = Path(bundle_id)
            if rel.is_absolute():
                raise ValueError(f"Unsafe bundle_id: expected relative path, got {bundle_id!r}")

            base_resolved = self._base_dir.resolve()
            bundle_dir = (self._base_dir / rel).resolve()
            try:
                bundle_dir.relative_to(base_resolved)
            except ValueError as exc:
                raise ValueError(f"Unsafe bundle_id: {bundle_id!r}") from exc

            manifest_path = bundle_dir / "manifest.json"
            if not manifest_path.exists():
                raise FileNotFoundError(f"Missing manifest: {manifest_path}")
            return [ArtifactBundle(path=bundle_dir, manifest=load_manifest(manifest_path))]

        bundles: list[ArtifactBundle] = []
        for bundle_dir in self.list_bundle_dirs():
            manifest_path = bundle_dir / "manifest.json"
            if not manifest_path.exists():
                continue
            try:
                bundles.append(
                    ArtifactBundle(
                        path=bundle_dir,
                        manifest=load_manifest(manifest_path),
                    )
                )
            except ValueError:
                continue

        bundles.sort(key=lambda item: item.manifest.created_at, reverse=True)
        return bundles

    def try_resolve(self, bundle_id: str | None = None) -> ArtifactBundle | None:
        """Resolve a bundle when available, returning ``None`` for invalid local state."""
        bundles = self.try_resolve_all(bundle_id)
        return bundles[0] if bundles else None

    def try_resolve_all(self, bundle_id: str | None = None) -> list[ArtifactBundle]:
        """Resolve available bundle candidates, returning empty for invalid local state."""
        try:
            return self.resolve_all(bundle_id)
        except (
            FileNotFoundError,
            OSError,
            UnicodeDecodeError,
            ValidationError,
            ValueError,
        ):
            return []
