"""Uncertainty summary helpers for artifact-backed predictions."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Literal

UncertaintyMethod = Literal["calibration_interval"]


@dataclass(frozen=True, slots=True)
class UncertaintySummary:
    """A calibrated uncertainty interval for one condition score."""

    method: UncertaintyMethod
    lower: float
    upper: float
    confidence_level: float | None
    caveat: str
    diagnostics: dict[str, float]


def build_uncertainty_summary(
    *,
    probability: float,
    method: str,
    payload: dict[str, Any] | None,
) -> UncertaintySummary | None:
    """Return an uncertainty summary only when the artifact manifest opts in."""
    if method == "none":
        return None
    if method != "calibration_interval":
        raise ValueError(f"Unsupported uncertainty method: {method}")
    if payload is None:
        raise ValueError("calibration_interval uncertainty requires an explicit artifact payload.")

    config = payload
    payload_method = config.get("method")
    if payload_method != "calibration_interval":
        raise ValueError(
            "calibration_interval uncertainty payload requires method='calibration_interval' "
            f"(got {payload_method!r})."
        )
    if "half_width" not in config:
        raise ValueError("calibration_interval uncertainty payload requires `half_width`.")
    half_width = float(config["half_width"])
    if not math.isfinite(half_width) or half_width < 0.0 or half_width > 1.0:
        raise ValueError(f"calibration_interval half_width must be between 0 and 1: {half_width}")
    confidence_level = config.get("confidence_level")
    if confidence_level is not None:
        parsed_confidence = float(confidence_level)
        if (
            not math.isfinite(parsed_confidence)
            or parsed_confidence <= 0.0
            or parsed_confidence > 1.0
        ):
            raise ValueError(
                "calibration_interval confidence_level must be in (0, 1] "
                f"(got {confidence_level!r})."
            )
    else:
        parsed_confidence = None
    diagnostics = _coerce_diagnostics(config.get("diagnostics"))
    caveat = str(
        config.get(
            "caveat",
            "Calibration interval declared by the artifact manifest; not an individual clinical "
            "confidence interval.",
        )
    )
    return UncertaintySummary(
        method="calibration_interval",
        lower=round(max(0.0, probability - half_width), 4),
        upper=round(min(1.0, probability + half_width), 4),
        confidence_level=parsed_confidence,
        caveat=caveat,
        diagnostics=diagnostics,
    )


def _coerce_diagnostics(value: object) -> dict[str, float]:
    """Return finite numeric diagnostics from optional artifact metadata."""
    if not isinstance(value, dict):
        return {}
    diagnostics: dict[str, float] = {}
    for key, item in value.items():
        if not isinstance(key, str) or not isinstance(item, str | int | float):
            continue
        parsed = float(item)
        if math.isfinite(parsed):
            diagnostics[key] = parsed
    return diagnostics
