"""Backend smoke tests."""

import datetime as dt
from collections.abc import Iterator
from pathlib import Path

import joblib  # type: ignore[import-untyped]
import pandas as pd  # type: ignore[import-untyped]
import pytest
from fastapi.testclient import TestClient
from sklearn.dummy import DummyClassifier  # type: ignore[import-untyped]
from sklearn.pipeline import Pipeline  # type: ignore[import-untyped]

from longevity_lab.api.main import create_app
from longevity_lab.artifacts.manifest import (
    ArtifactManifest,
    ConditionArtifact,
    DatasetInfo,
    save_manifest,
)
from longevity_lab.config import get_settings


def _write_api_bundle(
    artifacts_dir: Path,
    bundle_id: str = "bundle-api",
    *,
    created_at: dt.datetime | None = None,
) -> str:
    """Write a minimal loadable artifact bundle for API startup tests."""
    models_dir = artifacts_dir / "models"
    bundle_dir = models_dir / bundle_id
    bundle_dir.mkdir(parents=True)
    frame = pd.DataFrame(
        [
            {
                "age": 45,
                "bmi": 28.0,
                "smoker": True,
                "alcohol_servings_per_week": 10,
                "exercise_minutes_per_week": 60,
                "annual_aqi": 80,
            },
            {
                "age": 45,
                "bmi": 26.0,
                "smoker": False,
                "alcohol_servings_per_week": 4,
                "exercise_minutes_per_week": 180,
                "annual_aqi": 55,
            },
        ]
    )
    pipeline = Pipeline([("model", DummyClassifier(strategy="prior"))])
    pipeline.fit(frame, [1, 0])
    pipeline_path = bundle_dir / "heart_disease.joblib"
    joblib.dump(pipeline, pipeline_path)
    save_manifest(
        ArtifactManifest(
            created_at=created_at or dt.datetime.now(dt.UTC),
            dataset=DatasetInfo(name="brfss", version="test"),
            features=list(frame.columns),
            conditions=[
                ConditionArtifact(
                    condition_id="heart_disease",
                    pipeline_path=pipeline_path.name,
                    explanation_method="tree_path",
                )
            ],
        ),
        bundle_dir / "manifest.json",
    )
    return bundle_id


def _write_incomplete_api_bundle(
    artifacts_dir: Path,
    bundle_id: str = "bundle-incomplete",
    *,
    created_at: dt.datetime | None = None,
) -> str:
    """Write a parseable bundle manifest that references a missing pipeline."""
    bundle_dir = artifacts_dir / "models" / bundle_id
    bundle_dir.mkdir(parents=True)
    save_manifest(
        ArtifactManifest(
            created_at=created_at or dt.datetime.now(dt.UTC),
            dataset=DatasetInfo(name="brfss", version="test"),
            features=[
                "age",
                "bmi",
                "smoker",
                "alcohol_servings_per_week",
                "exercise_minutes_per_week",
                "annual_aqi",
            ],
            conditions=[
                ConditionArtifact(
                    condition_id="heart_disease",
                    pipeline_path="missing-heart-disease.joblib",
                    explanation_method="tree_path",
                )
            ],
        ),
        bundle_dir / "manifest.json",
    )
    return bundle_id


def _write_wrong_object_api_bundle(artifacts_dir: Path, bundle_id: str = "bundle-wrong") -> str:
    """Write a parseable bundle whose joblib file is not a serving pipeline."""
    bundle_dir = artifacts_dir / "models" / bundle_id
    bundle_dir.mkdir(parents=True)
    pipeline_path = bundle_dir / "heart_disease.joblib"
    joblib.dump({"not": "a pipeline"}, pipeline_path)
    save_manifest(
        ArtifactManifest(
            dataset=DatasetInfo(name="brfss", version="test"),
            features=[
                "age",
                "bmi",
                "smoker",
                "alcohol_servings_per_week",
                "exercise_minutes_per_week",
                "annual_aqi",
            ],
            conditions=[
                ConditionArtifact(
                    condition_id="heart_disease",
                    pipeline_path=pipeline_path.name,
                    explanation_method="tree_path",
                )
            ],
        ),
        bundle_dir / "manifest.json",
    )
    return bundle_id


def _write_corrupt_joblib_api_bundle(
    artifacts_dir: Path,
    bundle_id: str = "bundle-corrupt",
) -> str:
    """Write a parseable bundle whose joblib file cannot be loaded."""
    bundle_dir = artifacts_dir / "models" / bundle_id
    bundle_dir.mkdir(parents=True)
    pipeline_path = bundle_dir / "heart_disease.joblib"
    pipeline_path.write_bytes(b"not-a-valid-joblib")
    save_manifest(
        ArtifactManifest(
            dataset=DatasetInfo(name="brfss", version="test"),
            features=[
                "age",
                "bmi",
                "smoker",
                "alcohol_servings_per_week",
                "exercise_minutes_per_week",
                "annual_aqi",
            ],
            conditions=[
                ConditionArtifact(
                    condition_id="heart_disease",
                    pipeline_path=pipeline_path.name,
                    explanation_method="tree_path",
                )
            ],
        ),
        bundle_dir / "manifest.json",
    )
    return bundle_id


def _compare_payload() -> dict[str, dict[str, object]]:
    """Return a valid scenario comparison payload."""
    return {
        "baseline": {
            "age": 45,
            "bmi": 28.0,
            "smoker": True,
            "alcohol_servings_per_week": 10,
            "exercise_minutes_per_week": 60,
            "annual_aqi": 80,
        },
        "candidate": {
            "age": 45,
            "bmi": 26.0,
            "smoker": False,
            "alcohol_servings_per_week": 4,
            "exercise_minutes_per_week": 180,
            "annual_aqi": 55,
        },
    }


def _configured_client(
    monkeypatch: pytest.MonkeyPatch,
    *,
    artifacts_dir: Path,
    engine: str | None = None,
    bundle_id: str | None = None,
) -> Iterator[TestClient]:
    """Yield a TestClient with isolated settings."""
    monkeypatch.setenv("LONGEVITY_LAB_ARTIFACTS_DIR", str(artifacts_dir))
    if engine is None:
        monkeypatch.delenv("LONGEVITY_LAB_ENGINE", raising=False)
    else:
        monkeypatch.setenv("LONGEVITY_LAB_ENGINE", engine)
    if bundle_id is None:
        monkeypatch.delenv("LONGEVITY_LAB_ARTIFACT_BUNDLE", raising=False)
    else:
        monkeypatch.setenv("LONGEVITY_LAB_ARTIFACT_BUNDLE", bundle_id)

    get_settings.cache_clear()
    try:
        with TestClient(create_app()) as test_client:
            yield test_client
    finally:
        get_settings.cache_clear()


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[TestClient]:
    """Yield a lifespan-aware API test client isolated from local artifacts."""
    monkeypatch.setenv("LONGEVITY_LAB_ARTIFACTS_DIR", str(tmp_path / "artifacts"))
    monkeypatch.delenv("LONGEVITY_LAB_ENGINE", raising=False)
    monkeypatch.delenv("LONGEVITY_LAB_ARTIFACT_BUNDLE", raising=False)

    get_settings.cache_clear()
    try:
        with TestClient(create_app()) as test_client:
            yield test_client
    finally:
        get_settings.cache_clear()


def test_health(client: TestClient) -> None:
    """The health route should respond with an OK payload."""
    response = client.get("/api/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"


def test_metadata_bootstrap(client: TestClient) -> None:
    """The bootstrap route should return organs and conditions."""
    response = client.get("/api/metadata/bootstrap")
    assert response.status_code == 200
    payload = response.json()
    assert payload["contract_version"] == "v2"
    assert payload["organs"]
    assert payload["conditions"]
    assert payload["runtime"]["engine_mode"] == "demo"
    assert payload["runtime"]["engine_source"] == "fallback"
    model_metadata = payload["model_metadata"]
    assert model_metadata["model_mode"] == "demo"
    assert model_metadata["artifact_id"] is None
    assert model_metadata["data_vintage"] == "demo"
    assert model_metadata["dataset_name"] is None
    assert model_metadata["dataset_version"] is None
    assert model_metadata["explanation_methods"] == ["demo"]
    assert model_metadata["uncertainty_available"] is False
    assert model_metadata["uncertainty_methods"] == []
    assert model_metadata["contextual_geography"] == {
        "available": False,
        "levels": [],
        "source": None,
    }
    assert {item["field"] for item in payload["features"]} == {
        "age",
        "bmi",
        "smoker",
        "alcohol_servings_per_week",
        "exercise_minutes_per_week",
        "annual_aqi",
    }


def test_metadata_bootstrap_auto_selects_artifact_bundle(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Auto mode should prefer a valid local artifact bundle."""
    bundle_id = _write_api_bundle(tmp_path / "artifacts")
    for test_client in _configured_client(monkeypatch, artifacts_dir=tmp_path / "artifacts"):
        response = test_client.get("/api/metadata/bootstrap")
        assert response.status_code == 200
        payload = response.json()
        runtime = payload["runtime"]
        assert runtime["engine_mode"] == "artifact"
        assert runtime["engine_source"] == "auto"
        assert runtime["artifact_bundle_id"] == bundle_id
        model_metadata = payload["model_metadata"]
        assert model_metadata["model_mode"] == "artifact"
        assert model_metadata["artifact_id"] == bundle_id
        assert model_metadata["data_vintage"] == "test"
        assert model_metadata["dataset_name"] == "brfss"
        assert model_metadata["dataset_version"] == "test"
        assert model_metadata["dataset_retrieved_at"] is None
        assert model_metadata["explanation_methods"] == []
        assert model_metadata["uncertainty_available"] is False
        assert model_metadata["uncertainty_methods"] == []
        assert model_metadata["contextual_geography"] == {
            "available": True,
            "levels": ["state"],
            "source": "artifact_features",
        }


def test_metadata_bootstrap_explicit_demo_ignores_artifact_bundle(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Explicit demo mode should preserve the user's engine override."""
    _write_api_bundle(tmp_path / "artifacts")
    for test_client in _configured_client(
        monkeypatch,
        artifacts_dir=tmp_path / "artifacts",
        engine="demo",
    ):
        response = test_client.get("/api/metadata/bootstrap")
        assert response.status_code == 200
        runtime = response.json()["runtime"]
        assert runtime["engine_mode"] == "demo"
        assert runtime["engine_source"] == "explicit"
        assert runtime["artifact_bundle_id"] is None


def test_metadata_bootstrap_explicit_artifact_uses_selected_bundle(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Explicit artifact mode should load the selected bundle."""
    bundle_id = _write_api_bundle(tmp_path / "artifacts")
    for test_client in _configured_client(
        monkeypatch,
        artifacts_dir=tmp_path / "artifacts",
        engine="artifact",
        bundle_id=bundle_id,
    ):
        response = test_client.get("/api/metadata/bootstrap")
        assert response.status_code == 200
        runtime = response.json()["runtime"]
        assert runtime["engine_mode"] == "artifact"
        assert runtime["engine_source"] == "explicit"
        assert runtime["artifact_bundle_id"] == bundle_id


def test_metadata_bootstrap_auto_falls_back_on_invalid_bundle(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Auto mode should fall back to demo when local bundles are invalid."""
    (tmp_path / "artifacts" / "models" / "invalid-bundle").mkdir(parents=True)
    for test_client in _configured_client(monkeypatch, artifacts_dir=tmp_path / "artifacts"):
        response = test_client.get("/api/metadata/bootstrap")
        assert response.status_code == 200
        runtime = response.json()["runtime"]
        assert runtime["engine_mode"] == "demo"
        assert runtime["engine_source"] == "fallback"


def test_metadata_bootstrap_auto_falls_back_on_incomplete_bundle(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Auto mode should not crash when a manifest points at missing model files."""
    _write_incomplete_api_bundle(tmp_path / "artifacts")
    for test_client in _configured_client(monkeypatch, artifacts_dir=tmp_path / "artifacts"):
        response = test_client.get("/api/metadata/bootstrap")
        assert response.status_code == 200
        runtime = response.json()["runtime"]
        assert runtime["engine_mode"] == "demo"
        assert runtime["engine_source"] == "fallback"


def test_metadata_bootstrap_auto_falls_back_on_corrupt_bundle(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Auto mode should not crash when a bundle contains corrupt joblib files."""
    _write_corrupt_joblib_api_bundle(tmp_path / "artifacts")
    for test_client in _configured_client(monkeypatch, artifacts_dir=tmp_path / "artifacts"):
        response = test_client.get("/api/metadata/bootstrap")
        assert response.status_code == 200
        runtime = response.json()["runtime"]
        assert runtime["engine_mode"] == "demo"
        assert runtime["engine_source"] == "fallback"


def test_scenario_compare_auto_fallback_stays_usable_for_corrupt_bundle(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Auto fallback should still serve scenario comparisons after rejecting a bad bundle."""
    _write_corrupt_joblib_api_bundle(tmp_path / "artifacts")
    for test_client in _configured_client(monkeypatch, artifacts_dir=tmp_path / "artifacts"):
        response = test_client.post("/api/scenario/compare", json=_compare_payload())
        assert response.status_code == 200
        body = response.json()
        assert body["baseline"]["conditions"]
        assert body["candidate"]["conditions"]


def test_scenario_compare_auto_selected_artifact_reports_model_metadata(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Scenario compare should expose the same v2 model metadata as bootstrap."""
    bundle_id = _write_api_bundle(tmp_path / "artifacts")
    for test_client in _configured_client(monkeypatch, artifacts_dir=tmp_path / "artifacts"):
        response = test_client.post("/api/scenario/compare", json=_compare_payload())
        assert response.status_code == 200
        payload = response.json()
        assert payload["contract_version"] == "v2"
        assert payload["model_metadata"]["model_mode"] == "artifact"
        assert payload["model_metadata"]["artifact_id"] == bundle_id
        assert payload["model_metadata"]["data_vintage"] == "test"
        assert payload["model_metadata"]["explanation_methods"] == []
        assert payload["baseline"]["conditions"][0]["explanations"] == []
        assert payload["model_metadata"]["contextual_geography"]["levels"] == ["state"]


def test_metadata_bootstrap_auto_falls_back_on_wrong_object_bundle(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Auto mode should validate scoring before selecting artifact mode."""
    _write_wrong_object_api_bundle(tmp_path / "artifacts")
    for test_client in _configured_client(monkeypatch, artifacts_dir=tmp_path / "artifacts"):
        response = test_client.get("/api/metadata/bootstrap")
        assert response.status_code == 200
        runtime = response.json()["runtime"]
        assert runtime["engine_mode"] == "demo"
        assert runtime["engine_source"] == "fallback"


def test_metadata_bootstrap_auto_selects_older_valid_bundle(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Auto mode should keep trying older bundles when the newest bundle is invalid."""
    valid_bundle_id = _write_api_bundle(
        tmp_path / "artifacts",
        "bundle-valid",
        created_at=dt.datetime(2026, 1, 1, tzinfo=dt.UTC),
    )
    _write_incomplete_api_bundle(
        tmp_path / "artifacts",
        "bundle-newer-invalid",
        created_at=dt.datetime(2026, 2, 1, tzinfo=dt.UTC),
    )
    for test_client in _configured_client(monkeypatch, artifacts_dir=tmp_path / "artifacts"):
        response = test_client.get("/api/metadata/bootstrap")
        assert response.status_code == 200
        runtime = response.json()["runtime"]
        assert runtime["engine_mode"] == "artifact"
        assert runtime["engine_source"] == "auto"
        assert runtime["artifact_bundle_id"] == valid_bundle_id


def test_metadata_bootstrap_auto_falls_back_on_selected_missing_manifest(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Auto mode should fall back when the selected bundle has no manifest."""
    (tmp_path / "artifacts" / "models" / "selected-bad").mkdir(parents=True)
    for test_client in _configured_client(
        monkeypatch,
        artifacts_dir=tmp_path / "artifacts",
        bundle_id="selected-bad",
    ):
        response = test_client.get("/api/metadata/bootstrap")
        assert response.status_code == 200
        runtime = response.json()["runtime"]
        assert runtime["engine_mode"] == "demo"
        assert runtime["engine_source"] == "fallback"


def test_metadata_bootstrap_auto_falls_back_on_selected_corrupt_manifest(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Auto mode should fall back when the selected bundle manifest is unreadable."""
    bundle_dir = tmp_path / "artifacts" / "models" / "selected-bad"
    bundle_dir.mkdir(parents=True)
    (bundle_dir / "manifest.json").write_text("{not valid json", encoding="utf-8")
    for test_client in _configured_client(
        monkeypatch,
        artifacts_dir=tmp_path / "artifacts",
        bundle_id="selected-bad",
    ):
        response = test_client.get("/api/metadata/bootstrap")
        assert response.status_code == 200
        runtime = response.json()["runtime"]
        assert runtime["engine_mode"] == "demo"
        assert runtime["engine_source"] == "fallback"


def test_metadata_bootstrap_auto_falls_back_on_selected_schema_invalid_manifest(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Auto mode should fall back when the selected bundle manifest has invalid schema."""
    bundle_dir = tmp_path / "artifacts" / "models" / "selected-bad"
    bundle_dir.mkdir(parents=True)
    (bundle_dir / "manifest.json").write_text('{"schema_version": "bad"}\n', encoding="utf-8")
    for test_client in _configured_client(
        monkeypatch,
        artifacts_dir=tmp_path / "artifacts",
        bundle_id="selected-bad",
    ):
        response = test_client.get("/api/metadata/bootstrap")
        assert response.status_code == 200
        runtime = response.json()["runtime"]
        assert runtime["engine_mode"] == "demo"
        assert runtime["engine_source"] == "fallback"


def test_request_id_header_added(client: TestClient) -> None:
    """Responses should include an X-Request-ID header."""
    response = client.get("/api/health")
    assert response.status_code == 200
    request_id = response.headers.get("X-Request-ID")
    assert request_id is not None
    assert request_id


def test_request_id_header_preserved(client: TestClient) -> None:
    """If a client supplies X-Request-ID, it should be preserved."""
    inbound_request_id = "test-request-id"
    response = client.get("/api/health", headers={"X-Request-ID": inbound_request_id})
    assert response.status_code == 200
    assert response.headers.get("X-Request-ID") == inbound_request_id


def test_request_id_header_rejects_invalid_input(client: TestClient) -> None:
    """Invalid inbound request IDs should be replaced with a safe generated value."""
    inbound_request_id = "bad id"
    response = client.get("/api/health", headers={"X-Request-ID": inbound_request_id})
    assert response.status_code == 200
    request_id = response.headers.get("X-Request-ID")
    assert request_id is not None
    assert request_id != inbound_request_id
    assert len(request_id) == 32


def test_scenario_compare(client: TestClient) -> None:
    """The compare route should return baseline, candidate, and deltas."""
    response = client.post("/api/scenario/compare", json=_compare_payload())
    assert response.status_code == 200
    body = response.json()
    assert body["contract_version"] == "v2"
    assert body["model_metadata"]["model_mode"] == "demo"
    assert body["model_metadata"]["artifact_id"] is None
    assert body["model_metadata"]["data_vintage"] == "demo"
    assert body["model_metadata"]["explanation_methods"] == ["demo"]
    assert body["model_metadata"]["uncertainty_available"] is False
    assert body["model_metadata"]["contextual_geography"]["available"] is False
    assert body["baseline"]["conditions"]
    assert body["candidate"]["conditions"]
    assert body["organ_deltas"]
    condition = body["baseline"]["conditions"][0]
    assert "explanations" in condition
    assert "uncertainty" in condition
    assert condition["explanations"]
    assert condition["uncertainty"] is None
    assert set(condition["explanations"][0]) == {
        "feature",
        "display_name",
        "direction",
        "magnitude",
        "method",
        "caveat",
    }


def test_scenario_compare_missing_baseline_fields_uses_defaults(client: TestClient) -> None:
    """Missing baseline fields should fall back to safe schema defaults."""
    full_payload = {
        "baseline": {
            "age": 45,
            "bmi": 28.0,
            "smoker": True,
            "alcohol_servings_per_week": 10,
            "exercise_minutes_per_week": 60,
            "annual_aqi": 80,
        },
        "candidate": {
            "age": 45,
            "bmi": 26.0,
            "smoker": False,
            "alcohol_servings_per_week": 4,
            "exercise_minutes_per_week": 180,
            "annual_aqi": 55,
        },
    }
    expected = client.post("/api/scenario/compare", json=full_payload)
    assert expected.status_code == 200

    payload_missing = {
        **full_payload,
        "baseline": {
            "age": 45,
            "bmi": 28.0,
            "smoker": True,
            "alcohol_servings_per_week": 10,
        },
    }
    response = client.post("/api/scenario/compare", json=payload_missing)
    assert response.status_code == 200
    assert response.json() == expected.json()


def test_scenario_compare_missing_candidate_fields_uses_defaults(client: TestClient) -> None:
    """Missing candidate fields should fall back to safe schema defaults."""
    full_payload = {
        "baseline": {
            "age": 45,
            "bmi": 28.0,
            "smoker": True,
            "alcohol_servings_per_week": 10,
            "exercise_minutes_per_week": 60,
            "annual_aqi": 80,
        },
        "candidate": {
            "age": 45,
            "bmi": 26.0,
            "smoker": False,
            "alcohol_servings_per_week": 4,
            "exercise_minutes_per_week": 180,
            "annual_aqi": 55,
        },
    }
    expected = client.post("/api/scenario/compare", json=full_payload)
    assert expected.status_code == 200

    payload_missing = {
        **full_payload,
        "candidate": {
            "bmi": 26.0,
            "smoker": False,
            "alcohol_servings_per_week": 4,
            "exercise_minutes_per_week": 180,
            "annual_aqi": 55,
        },
    }
    response = client.post("/api/scenario/compare", json=payload_missing)
    assert response.status_code == 200
    assert response.json() == expected.json()


def test_scenario_compare_rejects_non_editable_brfss_v2_covariates(
    client: TestClient,
) -> None:
    """The public API should reject non-editable covariates in scenario payloads."""
    payload = _compare_payload()
    payload["baseline"].update(
        {
            "sex": "male",
            "race_ethnicity": "hispanic",
            "has_healthcare_coverage": True,
            "has_personal_doctor": True,
            "cost_barrier_to_care": False,
            "last_checkup_within_year": True,
            "sleep_hours_per_night": 7,
            "physical_health_days": 0,
            "mental_health_days": 2,
        }
    )
    payload["candidate"].update(
        {
            "sex": "female",
            "race_ethnicity": "white_non_hispanic",
            "has_healthcare_coverage": None,
            "has_personal_doctor": None,
            "cost_barrier_to_care": None,
            "last_checkup_within_year": None,
            "sleep_hours_per_night": None,
            "physical_health_days": None,
            "mental_health_days": None,
        }
    )

    response = client.post("/api/scenario/compare", json=payload)
    assert response.status_code == 422


def test_scenario_compare_out_of_range_still_422(client: TestClient) -> None:
    """Out-of-range values should still return a validation error."""
    payload = {
        "baseline": {
            "age": 10,
            "bmi": 28.0,
            "smoker": True,
            "alcohol_servings_per_week": 10,
            "exercise_minutes_per_week": 60,
            "annual_aqi": 80,
        },
        "candidate": {
            "age": 45,
            "bmi": 26.0,
            "smoker": False,
            "alcohol_servings_per_week": 4,
            "exercise_minutes_per_week": 180,
            "annual_aqi": 55,
        },
    }
    response = client.post("/api/scenario/compare", json=payload)
    assert response.status_code == 422


def test_scenario_compare_unknown_extra_field_still_422(client: TestClient) -> None:
    """Unknown extra fields should still return a validation error."""
    payload = {
        "baseline": {
            "age": 45,
            "bmi": 28.0,
            "smoker": True,
            "alcohol_servings_per_week": 10,
            "exercise_minutes_per_week": 60,
            "annual_aqi": 80,
            "unknown_extra": 1,
        },
        "candidate": {
            "age": 45,
            "bmi": 26.0,
            "smoker": False,
            "alcohol_servings_per_week": 4,
            "exercise_minutes_per_week": 180,
            "annual_aqi": 55,
        },
    }
    response = client.post("/api/scenario/compare", json=payload)
    assert response.status_code == 422
