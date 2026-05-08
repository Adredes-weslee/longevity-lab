"""Tests for public evidence bundle packaging and installation scripts."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path

import pandas as pd  # type: ignore[import-untyped]


def test_public_evidence_bundle_can_be_packaged_and_installed(tmp_path: Path) -> None:
    """The bundle scripts should create and safely install a small evidence archive."""
    data_dir = tmp_path / "data"
    output_dir = tmp_path / "dist"
    install_artifacts = tmp_path / "install" / "artifacts"
    bundle_id = "public-evidence-test"
    _write_minimal_processed_evidence(data_dir)

    subprocess.run(
        [
            sys.executable,
            "scripts/build_public_evidence_bundle.py",
            "--data-dir",
            str(data_dir),
            "--bundle-id",
            bundle_id,
            "--output-dir",
            str(output_dir),
        ],
        check=True,
    )

    archive_path = output_dir / f"{bundle_id}.zip"
    assert archive_path.exists()
    with zipfile.ZipFile(archive_path) as archive:
        names = set(archive.namelist())
    assert f"{bundle_id}/manifest.json" in names
    assert f"{bundle_id}/processed/context/context_county_year.parquet" in names
    assert f"{bundle_id}/processed/places/places_county_year.parquet" in names
    assert f"{bundle_id}/processed/validation/places_external_context_validation_2025.json" in names
    assert f"{bundle_id}/processed/reports/causal/bmi_diabetes/bmi_diabetes_report.json" in names

    env = os.environ.copy()
    env.update(
        {
            "LONGEVITY_LAB_EVIDENCE_BUNDLE": bundle_id,
            "LONGEVITY_LAB_EVIDENCE_BUNDLE_URL": archive_path.as_uri(),
            "LONGEVITY_LAB_EVIDENCE_BUNDLE_SHA256": _sha256_file(archive_path),
            "LONGEVITY_LAB_ARTIFACTS_DIR": str(install_artifacts),
        }
    )
    subprocess.run(
        [sys.executable, "scripts/download_evidence_bundle.py"],
        check=True,
        env=env,
    )

    installed_root = install_artifacts / "evidence" / bundle_id
    manifest = json.loads((installed_root / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["bundle_id"] == bundle_id
    assert manifest["roles"]["county_context"]["path"] == (
        "processed/context/context_county_year.parquet"
    )
    assert (installed_root / "processed" / "reports" / "causal" / "bmi_diabetes").exists()


def _write_minimal_processed_evidence(data_dir: Path) -> None:
    context_dir = data_dir / "processed" / "context"
    places_dir = data_dir / "processed" / "places"
    validation_dir = data_dir / "processed" / "validation"
    causal_dir = data_dir / "processed" / "reports" / "causal" / "bmi_diabetes"
    context_dir.mkdir(parents=True)
    places_dir.mkdir(parents=True)
    validation_dir.mkdir(parents=True)
    causal_dir.mkdir(parents=True)

    pd.DataFrame([{"year": 2023, "state_fips": "06", "geography_name": "California"}]).to_parquet(
        context_dir / "context_state_year.parquet", index=False
    )
    pd.DataFrame(
        [
            {
                "year": 2023,
                "state_fips": "06",
                "county_fips": "06001",
                "geography_name": "Alameda County, California",
            }
        ]
    ).to_parquet(context_dir / "context_county_year.parquet", index=False)
    pd.DataFrame(
        [
            {
                "release_year": 2025,
                "year": 2023,
                "state_fips": "06",
                "county_fips": "06001",
                "geography_name": "Alameda County, California",
            }
        ]
    ).to_parquet(places_dir / "places_county_year.parquet", index=False)
    (validation_dir / "places_external_context_validation_2025.json").write_text(
        json.dumps({"rows": [], "summary": {"conditions_compared": []}}),
        encoding="utf-8",
    )
    (causal_dir / "bmi_diabetes_report.json").write_text(
        json.dumps(
            {
                "question_id": "bmi_diabetes",
                "title": "BMI and diagnosed diabetes",
                "status": "exploratory_assumption_bound",
            }
        ),
        encoding="utf-8",
    )
    (causal_dir / "bmi_diabetes_report.md").write_text(
        "# BMI and diagnosed diabetes\n",
        encoding="utf-8",
    )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
