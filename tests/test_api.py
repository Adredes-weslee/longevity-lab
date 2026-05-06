"""Backend smoke tests."""

import datetime as dt
import json
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
    ContextFeatureManifest,
    DatasetInfo,
    save_manifest,
)
from longevity_lab.config import get_settings


def _write_api_bundle(
    artifacts_dir: Path,
    bundle_id: str = "bundle-api",
    *,
    created_at: dt.datetime | None = None,
    write_metrics: bool = False,
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
    metrics_path = bundle_dir / "heart_disease_metrics.json"
    if write_metrics:
        metrics_path.write_text(
            json.dumps(
                {
                    "condition_id": "heart_disease",
                    "rows_total": 2,
                    "rows_train": 1,
                    "rows_test": 1,
                    "target_positive_rate": 0.5,
                    "features": list(frame.columns),
                    "best_params": {"max_depth": 2},
                    "base_metrics": {
                        "average_precision": 0.6,
                        "roc_auc": 0.7,
                        "brier_score": 0.2,
                    },
                    "calibrated_metrics": {
                        "average_precision": 0.8,
                        "roc_auc": 0.9,
                        "brier_score": 0.1,
                    },
                    "no_aqi_metrics": {
                        "average_precision": 0.75,
                        "roc_auc": 0.85,
                        "brier_score": 0.12,
                    },
                    "no_pollutants_metrics": {
                        "average_precision": 0.78,
                        "roc_auc": 0.88,
                        "brier_score": 0.11,
                    },
                }
            )
            + "\n",
            encoding="utf-8",
        )
    save_manifest(
        ArtifactManifest(
            created_at=created_at or dt.datetime.now(dt.UTC),
            dataset=DatasetInfo(name="brfss", version="test"),
            features=list(frame.columns),
            conditions=[
                ConditionArtifact(
                    condition_id="heart_disease",
                    pipeline_path=pipeline_path.name,
                    metrics_path=metrics_path.name if write_metrics else None,
                    explanation_method="tree_path",
                )
            ],
        ),
        bundle_dir / "manifest.json",
    )
    return bundle_id


def _write_context_api_bundle(artifacts_dir: Path, bundle_id: str = "bundle-context") -> str:
    """Write an artifact bundle that declares active state-year context features."""
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
                "acs_poverty_percent": 25.0,
                "svi_overall_percentile": 0.75,
            },
            {
                "age": 45,
                "bmi": 26.0,
                "smoker": False,
                "alcohol_servings_per_week": 4,
                "exercise_minutes_per_week": 180,
                "annual_aqi": 55,
                "acs_poverty_percent": 8.0,
                "svi_overall_percentile": 0.25,
            },
        ]
    )
    pipeline = Pipeline([("model", DummyClassifier(strategy="prior"))])
    pipeline.fit(frame, [1, 0])
    pipeline_path = bundle_dir / "heart_disease.joblib"
    joblib.dump(pipeline, pipeline_path)
    metrics_path = bundle_dir / "heart_disease_metrics.json"
    metrics_path.write_text(
        json.dumps(
            {
                "condition_id": "heart_disease",
                "rows_total": 2,
                "rows_train": 1,
                "rows_test": 1,
                "target_positive_rate": 0.5,
                "features": list(frame.columns),
                "context_features": ["acs_poverty_percent", "svi_overall_percentile"],
                "context_feature_count": 2,
                "best_params": {"max_depth": 2},
                "base_metrics": {"average_precision": 0.6},
                "calibrated_metrics": {"average_precision": 0.82},
                "no_context_metrics": {"average_precision": 0.74},
                "no_aqi_metrics": {"average_precision": 0.78},
                "no_pollutants_metrics": {"average_precision": 0.79},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    lookup_path = bundle_dir / "context_state_year_lookup.json"
    lookup_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "feature_names": ["acs_poverty_percent", "svi_overall_percentile"],
                "join_keys": ["state_fips", "year"],
                "rows": [
                    {
                        "state_fips": "06",
                        "year": 2023,
                        "acs_poverty_percent": 25.0,
                        "svi_overall_percentile": 0.75,
                    },
                    {
                        "state_fips": "13",
                        "year": 2023,
                        "acs_poverty_percent": 8.0,
                        "svi_overall_percentile": 0.25,
                    },
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    save_manifest(
        ArtifactManifest(
            dataset=DatasetInfo(name="integrated_person_year", version="2023"),
            features=list(frame.columns),
            context_features=ContextFeatureManifest(
                feature_names=["acs_poverty_percent", "svi_overall_percentile"],
                source_ids=["census_acs5_api_context", "cdc_atsdr_svi_us_county_csv"],
                join_keys=["state_fips", "year"],
                data_vintage="ACS 2023 5-year; SVI 2022 county aggregation",
                lookup_path=lookup_path.name,
                default_values={"acs_poverty_percent": 12.0, "svi_overall_percentile": 0.5},
                caveats=[
                    "State-year context is background geography context, not a personal behavior.",
                ],
            ),
            conditions=[
                ConditionArtifact(
                    condition_id="heart_disease",
                    pipeline_path=pipeline_path.name,
                    metrics_path=metrics_path.name,
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


def _inactive_contextual_geography() -> dict[str, object]:
    """Return the inactive contextual geography metadata contract."""
    return {
        "available": False,
        "levels": [],
        "source": None,
        "feature_count": 0,
        "features": [],
        "caveat": None,
    }


def _configured_client(
    monkeypatch: pytest.MonkeyPatch,
    *,
    artifacts_dir: Path,
    data_dir: Path | None = None,
    engine: str | None = None,
    bundle_id: str | None = None,
) -> Iterator[TestClient]:
    """Yield a TestClient with isolated settings."""
    monkeypatch.setenv("LONGEVITY_LAB_DATA_DIR", str(data_dir or artifacts_dir.parent / "data"))
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
    monkeypatch.setenv("LONGEVITY_LAB_DATA_DIR", str(tmp_path / "data"))
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
    assert model_metadata["contextual_geography"] == _inactive_contextual_geography()
    assert payload["geography"] == {
        "supported_levels": ["state"],
        "default_year": 2023,
        "context_lookup_active": False,
        "geographies_endpoint": "/api/context/geographies",
        "caveat": (
            "Only state-year geography context is selectable. The selected state is "
            "background context, not a personal behavior input."
        ),
    }
    assert {item["field"] for item in payload["features"]} == {
        "age",
        "bmi",
        "smoker",
        "alcohol_servings_per_week",
        "exercise_minutes_per_week",
        "annual_aqi",
        "pm25_mean",
        "ozone_mean",
    }


def test_context_geographies_missing_table_returns_state_options(client: TestClient) -> None:
    """The context geography route should be safe and state-year-only without local data."""
    response = client.get("/api/context/geographies?year=2023")

    assert response.status_code == 200
    payload = response.json()
    assert payload["contract_version"] == "v2"
    assert payload["selected_year"] == 2023
    assert payload["supported_levels"] == ["state"]
    assert payload["readiness"]["active"] is False
    assert payload["readiness"]["table_exists"] is False
    assert not Path(payload["readiness"]["table_path"]).is_absolute()
    assert payload["options"]
    assert {option["level"] for option in payload["options"]} == {"state"}
    assert all(option["context_available"] is False for option in payload["options"])


def test_model_cards_demo_reports_unavailable(client: TestClient) -> None:
    """Demo mode should expose a stable unavailable model-card response."""
    response = client.get("/api/models/cards")
    assert response.status_code == 200
    payload = response.json()
    assert payload["contract_version"] == "v2"
    assert payload["available"] is False
    assert payload["artifact_id"] is None
    assert payload["condition_cards"] == []
    assert payload["model_metadata"]["model_mode"] == "demo"


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
        assert model_metadata["contextual_geography"] == _inactive_contextual_geography()


def test_model_cards_artifact_surfaces_condition_metrics(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Artifact mode should expose metrics from trusted local model-card JSON files."""
    bundle_id = _write_api_bundle(tmp_path / "artifacts", write_metrics=True)
    for test_client in _configured_client(monkeypatch, artifacts_dir=tmp_path / "artifacts"):
        response = test_client.get("/api/models/cards")
        assert response.status_code == 200
        payload = response.json()
        assert payload["available"] is True
        assert payload["artifact_id"] == bundle_id
        assert payload["model_metadata"]["model_mode"] == "artifact"
        assert payload["condition_cards"][0]["condition_id"] == "heart_disease"
        assert payload["condition_cards"][0]["label"] == "Heart disease"
        assert payload["condition_cards"][0]["metrics_available"] is True
        assert payload["condition_cards"][0]["rows_total"] == 2
        assert payload["condition_cards"][0]["feature_count"] == 6
        assert payload["condition_cards"][0]["calibrated_metrics"]["roc_auc"] == 0.9
        assert payload["condition_cards"][0]["aqi_average_precision_delta"] == pytest.approx(0.05)
        assert payload["condition_cards"][0]["pollutant_average_precision_delta"] == pytest.approx(
            0.02
        )


def test_model_cards_artifact_tolerates_corrupt_metrics(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Model cards should not 500 when optional metrics JSON is corrupt."""
    bundle_id = _write_api_bundle(tmp_path / "artifacts", write_metrics=True)
    metrics_path = tmp_path / "artifacts" / "models" / bundle_id / "heart_disease_metrics.json"
    metrics_path.write_text("{not-json", encoding="utf-8")

    for test_client in _configured_client(monkeypatch, artifacts_dir=tmp_path / "artifacts"):
        response = test_client.get("/api/models/cards")
        assert response.status_code == 200
        payload = response.json()
        assert payload["available"] is False
        assert payload["artifact_id"] == bundle_id
        assert payload["condition_cards"][0]["metrics_available"] is False


def test_model_cards_use_nested_active_bundle_id(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Model cards should use the same nested bundle ID as the active scorer."""
    bundle_id = _write_api_bundle(
        tmp_path / "artifacts",
        bundle_id="group/bundle-nested",
        write_metrics=True,
    )

    for test_client in _configured_client(
        monkeypatch,
        artifacts_dir=tmp_path / "artifacts",
        engine="artifact",
        bundle_id=bundle_id,
    ):
        bootstrap = test_client.get("/api/metadata/bootstrap").json()
        cards = test_client.get("/api/models/cards").json()

        assert bootstrap["runtime"]["artifact_bundle_id"] == bundle_id
        assert bootstrap["model_metadata"]["artifact_id"] == bundle_id
        assert cards["artifact_id"] == bundle_id
        assert cards["model_metadata"]["artifact_id"] == bundle_id
        assert cards["available"] is True
        assert cards["condition_cards"][0]["condition_id"] == "heart_disease"


def test_auto_mode_uses_nested_selected_bundle_id(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Auto mode should validate and serve a selected nested artifact bundle."""
    bundle_id = _write_api_bundle(
        tmp_path / "artifacts",
        bundle_id="group/bundle-nested",
        write_metrics=True,
    )

    for test_client in _configured_client(
        monkeypatch,
        artifacts_dir=tmp_path / "artifacts",
        bundle_id=bundle_id,
    ):
        bootstrap = test_client.get("/api/metadata/bootstrap").json()
        compare = test_client.post("/api/scenario/compare", json=_compare_payload()).json()
        cards = test_client.get("/api/models/cards").json()

        assert bootstrap["runtime"]["engine_mode"] == "artifact"
        assert bootstrap["runtime"]["engine_source"] == "auto"
        assert bootstrap["runtime"]["artifact_bundle_id"] == bundle_id
        assert compare["model_metadata"]["artifact_id"] == bundle_id
        assert cards["artifact_id"] == bundle_id
        assert cards["available"] is True


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
        assert [item["condition_id"] for item in response.json()["conditions"]] == ["heart_disease"]
        assert [item["organ_id"] for item in response.json()["organs"]] == ["heart"]


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
        assert payload["model_metadata"]["contextual_geography"] == _inactive_contextual_geography()
        assert [item["condition_id"] for item in payload["candidate"]["conditions"]] == [
            "heart_disease"
        ]
        assert [item["organ_id"] for item in payload["organ_deltas"]] == ["heart"]


def test_artifact_scenario_compare_accepts_geography_without_score_change(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Artifact scoring should accept geography metadata but not use ACS/SVI yet."""
    _write_api_bundle(tmp_path / "artifacts")
    for test_client in _configured_client(monkeypatch, artifacts_dir=tmp_path / "artifacts"):
        expected = test_client.post("/api/scenario/compare", json=_compare_payload())
        payload = {
            **_compare_payload(),
            "geography": {"level": "state", "state_fips": "06", "year": 2023},
        }
        response = test_client.post("/api/scenario/compare", json=payload)

        assert response.status_code == 200
        assert response.json() == expected.json()


def test_context_feature_artifact_is_not_marked_geography_active(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Context-like feature names alone must not activate geography-aware scoring."""
    bundle_id = _write_api_bundle(tmp_path / "artifacts")
    bundle_dir = tmp_path / "artifacts" / "models" / bundle_id
    manifest = json.loads((bundle_dir / "manifest.json").read_text(encoding="utf-8"))
    manifest["features"].extend(["acs_poverty_percent", "svi_overall_percentile"])
    (bundle_dir / "manifest.json").write_text(
        json.dumps(manifest) + "\n",
        encoding="utf-8",
    )

    for test_client in _configured_client(monkeypatch, artifacts_dir=tmp_path / "artifacts"):
        bootstrap = test_client.get("/api/metadata/bootstrap").json()
        evidence = test_client.get("/api/evidence/status").json()

        assert (
            bootstrap["model_metadata"]["contextual_geography"] == _inactive_contextual_geography()
        )
        context_gap = next(
            gap for gap in evidence["inactive_gaps"] if gap["gap_id"] == "context_not_active"
        )
        assert context_gap["evidence"] == [
            "acs_poverty_percent",
            "svi_overall_percentile",
        ]
        assert "does not declare context feature lookup provenance" in context_gap["explanation"]


def test_context_manifest_artifact_marks_state_year_context_active(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Artifacts with manifest context metadata should activate ACS/SVI evidence surfaces."""
    bundle_id = _write_context_api_bundle(tmp_path / "artifacts")

    for test_client in _configured_client(monkeypatch, artifacts_dir=tmp_path / "artifacts"):
        bootstrap = test_client.get("/api/metadata/bootstrap").json()
        evidence = test_client.get("/api/evidence/status").json()
        cards = test_client.get("/api/models/cards").json()

        assert bootstrap["runtime"]["artifact_bundle_id"] == bundle_id
        assert bootstrap["model_metadata"]["contextual_geography"] == {
            "available": True,
            "levels": ["state"],
            "source": "census_acs5_api_context, cdc_atsdr_svi_us_county_csv",
            "feature_count": 2,
            "features": ["acs_poverty_percent", "svi_overall_percentile"],
            "caveat": (
                "State-year context is background geography context, not a personal behavior."
            ),
        }
        sources = {item["source_id"]: item for item in evidence["sources"]}
        assert sources["census_acs5_api_context"]["role"] == "active_model"
        assert sources["census_acs5_api_context"]["active_in_model"] is True
        assert sources["cdc_atsdr_svi_us_county_csv"]["role"] == "active_model"
        gap_ids = {item["gap_id"] for item in evidence["inactive_gaps"]}
        assert "context_not_active" not in gap_ids
        assert "county_context_not_active" in gap_ids

        card = cards["condition_cards"][0]
        assert card["context_feature_count"] == 2
        assert card["context_features"] == ["acs_poverty_percent", "svi_overall_percentile"]
        assert card["context_average_precision_delta"] == pytest.approx(0.08)


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


def test_scenario_compare_accepts_optional_state_geography_without_score_change(
    client: TestClient,
) -> None:
    """Selecting state-year geography should not affect demo scores in PR 19."""
    expected = client.post("/api/scenario/compare", json=_compare_payload())
    assert expected.status_code == 200

    payload = {
        **_compare_payload(),
        "geography": {"level": "state", "state_fips": "06", "year": 2023},
    }
    response = client.post("/api/scenario/compare", json=payload)

    assert response.status_code == 200
    assert response.json() == expected.json()


def test_scenario_compare_rejects_county_geography(client: TestClient) -> None:
    """The public compare contract should not expose county-level prediction semantics."""
    payload = {
        **_compare_payload(),
        "geography": {"level": "county", "state_fips": "06", "year": 2023},
    }

    response = client.post("/api/scenario/compare", json=payload)

    assert response.status_code == 422


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
