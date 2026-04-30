"""Tests for BRFSS download-specific filename handling."""

from __future__ import annotations

from pathlib import Path

import pytest

from longevity_lab.pipeline.download_brfss import _brfss_urls, _ensure_canonical_xpt_name


class _FakeCandidate:
    """Minimal path-like object for testing extracted filename normalization."""

    def __init__(self, raw_dir: Path, name: str, *, payload: bytes = b"xpt") -> None:
        self._raw_dir = raw_dir
        self.name = name
        self._payload = payload
        self.replaced_to: Path | None = None

    def is_file(self) -> bool:
        return True

    def replace(self, target: Path) -> Path:
        self.replaced_to = target
        target.write_bytes(self._payload)
        return target

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, _FakeCandidate):
            return NotImplemented
        return self.name < other.name

    def __str__(self) -> str:
        return str(self._raw_dir / self.name)


def test_ensure_canonical_xpt_name_keeps_canonical_file(tmp_path: Path) -> None:
    """The canonical filename should be preserved when it already exists."""
    raw_dir = tmp_path / "brfss"
    raw_dir.mkdir()
    canonical = raw_dir / "LLCP2023.XPT"
    canonical.write_bytes(b"xpt")

    resolved = _ensure_canonical_xpt_name(raw_dir, year=2023)

    assert resolved == canonical
    assert canonical.exists()


def test_ensure_canonical_xpt_name_renames_trailing_space_variant(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A trailing-space zip member should be normalized to the canonical local name."""
    raw_dir = tmp_path / "brfss"
    raw_dir.mkdir()
    candidate = _FakeCandidate(raw_dir, "LLCP2023.XPT ")
    monkeypatch.setattr(
        Path,
        "iterdir",
        lambda self: iter([candidate]) if self == raw_dir else iter(()),
    )

    resolved = _ensure_canonical_xpt_name(raw_dir, year=2023)

    assert resolved == raw_dir / "LLCP2023.XPT"
    assert resolved.exists()
    assert candidate.replaced_to == resolved


def test_ensure_canonical_xpt_name_rejects_multiple_variants(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Multiple variants that collapse to the same canonical name should fail fast."""
    raw_dir = tmp_path / "brfss"
    raw_dir.mkdir()
    candidates = [
        _FakeCandidate(raw_dir, "LLCP2023.XPT "),
        _FakeCandidate(raw_dir, "LLCP2023.XPT  "),
    ]
    monkeypatch.setattr(
        Path,
        "iterdir",
        lambda self: iter(candidates) if self == raw_dir else iter(()),
    )

    with pytest.raises(FileExistsError):
        _ensure_canonical_xpt_name(raw_dir, year=2023)


def test_brfss_urls_are_registry_backed() -> None:
    """BRFSS URLs should still match the CDC v1 paths after registry refactor."""
    microdata_url, codebook_url = _brfss_urls(2023)

    assert microdata_url == "https://www.cdc.gov/brfss/annual_data/2023/files/LLCP2023XPT.zip"
    assert codebook_url == (
        "https://www.cdc.gov/brfss/annual_data/2023/zip/codebook23_llcp-v2-508.zip"
    )


def test_brfss_urls_reject_unsupported_year() -> None:
    """The current BRFSS registry remains pinned to supported years."""
    with pytest.raises(NotImplementedError):
        _brfss_urls(2022)
