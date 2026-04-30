"""Tests for pipeline common utilities."""

import json
import urllib.request
import zipfile
from pathlib import Path

import pytest

from longevity_lab.pipeline.common import (
    collect_file_provenance,
    default_data_dir,
    download_file,
    extract_zip,
    parse_years_csv,
    sha256_file,
    write_provenance_json,
)


def test_parse_years_csv() -> None:
    """parse_years_csv should parse comma-separated years."""
    assert parse_years_csv("2021,2022, 2023") == [2021, 2022, 2023]


def test_default_data_dir_points_to_repo_root() -> None:
    """Pipeline CLIs should default to the repo-root data directory, not cwd-relative data/."""
    expected = Path(__file__).resolve().parents[1] / "data"
    assert default_data_dir() == expected


def test_sha256_file(tmp_path: Path) -> None:
    """sha256_file should return a stable hex digest."""
    path = tmp_path / "hello.txt"
    path.write_text("hello", encoding="utf-8")
    digest = sha256_file(path)
    assert digest == "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"


def test_collect_file_provenance(tmp_path: Path) -> None:
    """collect_file_provenance should include size and sha256."""
    root = tmp_path / "root"
    root.mkdir()
    file_path = root / "file.bin"
    file_path.write_bytes(b"\x00\x01\x02")
    item = collect_file_provenance(file_path, url="https://example.com/file.bin", root=root)
    assert item.path == "file.bin"
    assert item.bytes == 3
    assert item.sha256
    assert item.url == "https://example.com/file.bin"


def test_collect_file_provenance_rejects_non_root(tmp_path: Path) -> None:
    """collect_file_provenance should error if root is unrelated."""
    other_root = tmp_path / "other"
    other_root.mkdir()
    file_path = tmp_path / "file.bin"
    file_path.write_bytes(b"\x00")
    with pytest.raises(ValueError):
        collect_file_provenance(file_path, root=other_root)


def test_extract_zip_extracts_files(tmp_path: Path) -> None:
    """extract_zip should extract all members under the destination."""
    zip_path = tmp_path / "sample.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.writestr("a.txt", "hello")

    dest_dir = tmp_path / "out"
    extracted = extract_zip(zip_path, dest_dir, dry_run=False)

    assert (dest_dir / "a.txt") in extracted
    assert (dest_dir / "a.txt").read_text(encoding="utf-8") == "hello"


def test_extract_zip_rejects_path_traversal(tmp_path: Path) -> None:
    """extract_zip should prevent Zip Slip path traversal attacks."""
    zip_path = tmp_path / "evil.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.writestr("../evil.txt", "pwnd")

    dest_dir = tmp_path / "out"
    with pytest.raises(ValueError):
        extract_zip(zip_path, dest_dir, dry_run=False)


def test_extract_zip_preserves_relative_dest_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """extract_zip should return relative paths when dest_dir is relative."""
    zip_path = tmp_path / "sample.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.writestr("a.txt", "hello")

    monkeypatch.chdir(tmp_path)
    dest_dir = Path("out")
    extracted = extract_zip(zip_path, dest_dir, dry_run=False)

    assert all(not path.is_absolute() for path in extracted)
    assert (tmp_path / "out" / "a.txt").read_text(encoding="utf-8") == "hello"


def test_download_file_cleans_up_part_file_on_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """download_file should not leave behind a partial *.part file after failure."""

    class DummyResponse:
        def __init__(self) -> None:
            self._calls = 0

        def read(self, _size: int) -> bytes:
            self._calls += 1
            if self._calls == 1:
                return b"hello"
            raise OSError("simulated read failure")

        def __enter__(self) -> "DummyResponse":
            return self

        def __exit__(
            self,
            exc_type: type[BaseException] | None,
            exc: BaseException | None,
            tb: object | None,
        ) -> None:
            return None

    def dummy_urlopen(_request: object, timeout: float | None = None) -> DummyResponse:
        return DummyResponse()

    monkeypatch.setattr(urllib.request, "urlopen", dummy_urlopen)

    dest_path = tmp_path / "file.bin"
    with pytest.raises(RuntimeError):
        download_file(
            "https://example.com/file.bin",
            dest_path,
            force=True,
            dry_run=False,
            retries=1,
        )

    assert not dest_path.exists()
    assert not dest_path.with_suffix(dest_path.suffix + ".part").exists()


def test_write_provenance_json_serializes_slotted_dataclasses(tmp_path: Path) -> None:
    """write_provenance_json should serialize FileProvenance even with slots enabled."""
    root = tmp_path / "root"
    root.mkdir()
    file_path = root / "file.bin"
    file_path.write_bytes(b"\x00\x01")

    out_path = tmp_path / "prov.json"
    item = collect_file_provenance(file_path, url="https://example.com/file.bin", root=root)
    write_provenance_json(
        out_path,
        dataset_name="unit_test",
        dataset_version="1",
        sources=["https://example.com/file.bin"],
        files=[item],
    )

    payload = json.loads(out_path.read_text(encoding="utf-8"))
    assert payload["dataset_name"] == "unit_test"
    assert payload["files"] == [
        {
            "path": "file.bin",
            "bytes": 2,
            "sha256": item.sha256,
            "url": "https://example.com/file.bin",
        }
    ]
