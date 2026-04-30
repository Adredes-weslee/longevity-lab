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
    if "half_width" not in config:
        raise ValueError("calibration_interval uncertainty payload requires `half_width`.")
    half_width = float(config["half_width"])
    if not math.isfinite(half_width) or half_width < 0.0 or half_width > 1.0:
        raise ValueError(f"calibration_interval half_width must be between 0 and 1: {half_width}")
    confidence_level = config.get("confidence_level")
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
        confidence_level=float(confidence_level) if confidence_level is not None else None,
        caveat=caveat,
    )
