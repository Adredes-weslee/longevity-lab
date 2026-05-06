"""Service for exposing model-card metrics from trusted local artifact bundles."""

from __future__ import annotations

import json
from json import JSONDecodeError
from pathlib import Path
from typing import Any

from longevity_lab.api.schemas import (
    ConditionModelCardResponse,
    ModelCardBundleResponse,
    ModelMetadataResponse,
    ModelMetricSetResponse,
)
from longevity_lab.artifacts.manifest import ConditionArtifact
from longevity_lab.artifacts.store import ArtifactBundle, ArtifactStore
from longevity_lab.domain.catalog import CONDITIONS

_CONDITION_LABELS = {condition.condition_id: condition.label for condition in CONDITIONS}


class ModelCardService:
    """Load active model-card metrics from the local artifact store."""

    def __init__(
        self,
        *,
        artifact_store: ArtifactStore,
        model_metadata: ModelMetadataResponse,
    ) -> None:
        """Store active model metadata and artifact lookup state."""
        self._artifact_store = artifact_store
        self._model_metadata = model_metadata

    def get_model_cards(self) -> ModelCardBundleResponse:
        """Return model-card metrics for the active artifact bundle when available."""
        artifact_id = self._model_metadata.artifact_id
        if self._model_metadata.model_mode != "artifact" or artifact_id is None:
            return ModelCardBundleResponse(
                model_metadata=self._model_metadata,
                available=False,
                artifact_id=None,
                message="Model-card metrics require an active artifact-backed bundle.",
            )

        bundle = self._artifact_store.try_resolve(artifact_id)
        if bundle is None:
            return ModelCardBundleResponse(
                model_metadata=self._model_metadata,
                available=False,
                artifact_id=artifact_id,
                message="The active artifact bundle could not be resolved locally.",
            )

        condition_cards = [
            _build_condition_card(bundle=bundle, condition=condition)
            for condition in bundle.manifest.conditions
        ]
        return ModelCardBundleResponse(
            model_metadata=self._model_metadata,
            available=any(card.metrics_available for card in condition_cards),
            artifact_id=artifact_id,
            generated_from=f"{artifact_id}/manifest.json",
            condition_cards=condition_cards,
            message="Loaded model-card metrics from the active local artifact bundle.",
        )


def _build_condition_card(
    *,
    bundle: ArtifactBundle,
    condition: ConditionArtifact,
) -> ConditionModelCardResponse:
    """Build one condition card from its metrics JSON if present."""
    label = _CONDITION_LABELS.get(condition.condition_id, condition.condition_id)
    if condition.metrics_path is None:
        return ConditionModelCardResponse(
            condition_id=condition.condition_id,
            label=label,
            metrics_available=False,
        )

    metrics_path = _safe_bundle_path(bundle.path, condition.metrics_path)
    if metrics_path is None or not metrics_path.exists():
        return ConditionModelCardResponse(
            condition_id=condition.condition_id,
            label=label,
            metrics_available=False,
            metrics_path=condition.metrics_path,
        )

    try:
        raw_payload = json.loads(metrics_path.read_text(encoding="utf-8"))
    except (OSError, JSONDecodeError, UnicodeDecodeError):
        return ConditionModelCardResponse(
            condition_id=condition.condition_id,
            label=label,
            metrics_available=False,
            metrics_path=condition.metrics_path,
        )
    if not isinstance(raw_payload, dict):
        return ConditionModelCardResponse(
            condition_id=condition.condition_id,
            label=label,
            metrics_available=False,
            metrics_path=condition.metrics_path,
        )
    payload: dict[str, Any] = raw_payload
    context_features = _context_features(bundle=bundle, payload=payload)
    return ConditionModelCardResponse(
        condition_id=str(payload.get("condition_id", condition.condition_id)),
        label=label,
        metrics_available=True,
        metrics_path=condition.metrics_path,
        rows_total=_optional_int(payload.get("rows_total")),
        rows_train=_optional_int(payload.get("rows_train")),
        rows_test=_optional_int(payload.get("rows_test")),
        positive_rate=_optional_float(payload.get("target_positive_rate")),
        feature_count=len(payload.get("features", []))
        if isinstance(payload.get("features"), list)
        else None,
        features=[str(item) for item in payload.get("features", [])]
        if isinstance(payload.get("features"), list)
        else [],
        context_feature_count=len(context_features),
        context_features=context_features,
        best_params=_coerce_best_params(payload.get("best_params")),
        base_metrics=_metric_set(payload.get("base_metrics")),
        calibrated_metrics=_metric_set(payload.get("calibrated_metrics")),
        no_context_metrics=_metric_set(payload.get("no_context_metrics")),
        no_aqi_metrics=_metric_set(payload.get("no_aqi_metrics")),
        no_pollutants_metrics=_metric_set(payload.get("no_pollutants_metrics")),
        context_average_precision_delta=_average_precision_delta(
            payload,
            ablation_key="no_context_metrics",
        ),
        aqi_average_precision_delta=_average_precision_delta(payload),
        pollutant_average_precision_delta=_average_precision_delta(
            payload,
            ablation_key="no_pollutants_metrics",
        ),
    )


def _context_features(
    *,
    bundle: ArtifactBundle,
    payload: dict[str, Any],
) -> list[str]:
    if bundle.manifest.context_features is None:
        return []
    payload_features = payload.get("context_features")
    if isinstance(payload_features, list):
        return [str(item) for item in payload_features]
    return list(bundle.manifest.context_features.feature_names)


def _safe_bundle_path(bundle_dir: Path, relative_path: str) -> Path | None:
    """Resolve a relative artifact path while preventing bundle traversal."""
    rel = Path(relative_path)
    if rel.is_absolute():
        return None
    base = bundle_dir.resolve()
    resolved = (bundle_dir / rel).resolve()
    try:
        resolved.relative_to(base)
    except ValueError:
        return None
    return resolved


def _metric_set(value: object) -> ModelMetricSetResponse:
    """Coerce a metrics mapping into the API response contract."""
    if not isinstance(value, dict):
        return ModelMetricSetResponse()
    return ModelMetricSetResponse(
        average_precision=_optional_float(value.get("average_precision")),
        roc_auc=_optional_float(value.get("roc_auc")),
        brier_score=_optional_float(value.get("brier_score")),
    )


def _average_precision_delta(
    payload: dict[str, Any],
    *,
    ablation_key: str = "no_aqi_metrics",
) -> float | None:
    """Return calibrated average-precision lift over an ablation variant."""
    calibrated = _metric_set(payload.get("calibrated_metrics")).average_precision
    ablation = _metric_set(payload.get(ablation_key)).average_precision
    if calibrated is None or ablation is None:
        return None
    return calibrated - ablation


def _coerce_best_params(value: object) -> dict[str, Any]:
    """Return JSON-compatible best-parameter values."""
    if not isinstance(value, dict):
        return {}
    return {
        str(key): item
        for key, item in value.items()
        if item is None or isinstance(item, str | int | float | bool)
    }


def _optional_float(value: object) -> float | None:
    """Coerce an optional numeric value to float."""
    if value is None:
        return None
    if not isinstance(value, str | int | float):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _optional_int(value: object) -> int | None:
    """Coerce an optional numeric value to int."""
    if value is None:
        return None
    if not isinstance(value, str | int | float):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
