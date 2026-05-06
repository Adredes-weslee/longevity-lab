"""Question registry loader for the non-serving causal workbench."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

REPO_ROOT = Path(__file__).resolve().parents[3]

QUESTION_ALIASES: dict[str, str] = {
    "smoking_lung": "smoking_chronic_lung_disease",
    "activity_diabetes": "physical_activity_diabetes",
}

CONFIG_FILE_BY_QUESTION: dict[str, str] = {
    "smoking_chronic_lung_disease": "smoking_lung.yaml",
    "physical_activity_diabetes": "activity_diabetes.yaml",
    "bmi_diabetes": "bmi_diabetes.yaml",
    "alcohol_depression": "alcohol_depression.yaml",
}


@dataclass(frozen=True, slots=True)
class CausalQuestionSpec:
    """Structured question metadata from ``conf/causal/questions.yaml``."""

    question_id: str
    title: str
    treatment_name: str
    treatment_contrast: str
    outcome_name: str
    outcome_label_field: str
    outcome_timing: str
    estimand: dict[str, Any]
    negative_control_outcomes: tuple[str, ...]
    negative_control_exposures: tuple[str, ...]
    sensitivity_checks: tuple[str, ...]
    dag_version: str
    dag_edges: tuple[str, ...]
    residual_risks: tuple[str, ...]
    predictive_separation: str


def default_question_registry_path() -> Path:
    """Return the repo-local causal question registry path."""
    return REPO_ROOT / "conf" / "causal" / "questions.yaml"


def resolve_repo_path(path: Path) -> Path:
    """Resolve a repo-local path independent of the caller's current directory."""
    return path if path.is_absolute() else REPO_ROOT / path


def resolve_question_id(question_id_or_alias: str) -> str:
    """Resolve a CLI/config alias to the canonical registry question id."""
    return QUESTION_ALIASES.get(question_id_or_alias, question_id_or_alias)


def default_config_path_for_question(question_id_or_alias: str) -> Path:
    """Return the concrete run-config path for a registry question id or alias."""
    question_id = resolve_question_id(question_id_or_alias)
    try:
        filename = CONFIG_FILE_BY_QUESTION[question_id]
    except KeyError as exc:
        message = f"No default causal run config for question: {question_id_or_alias}"
        raise ValueError(message) from exc
    return REPO_ROOT / "conf" / "causal" / filename


def load_question_registry(path: Path | None = None) -> dict[str, CausalQuestionSpec]:
    """Load all causal question specs keyed by canonical question id."""
    registry_path = resolve_repo_path(path) if path else default_question_registry_path()
    payload = yaml.safe_load(registry_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Causal question registry is not a mapping: {registry_path}")
    questions = payload.get("questions")
    if not isinstance(questions, list):
        raise ValueError(f"Causal question registry has no questions list: {registry_path}")

    registry: dict[str, CausalQuestionSpec] = {}
    for raw_question in questions:
        if not isinstance(raw_question, dict):
            raise ValueError(f"Causal question registry item is not a mapping: {registry_path}")
        spec = _question_from_mapping(raw_question)
        registry[spec.question_id] = spec
    return registry


def load_question_spec(
    question_id_or_alias: str,
    *,
    path: Path | None = None,
) -> CausalQuestionSpec:
    """Load one causal question spec by canonical id or supported CLI alias."""
    question_id = resolve_question_id(question_id_or_alias)
    registry = load_question_registry(path)
    try:
        return registry[question_id]
    except KeyError as exc:
        raise ValueError(f"Causal question registry has no question id: {question_id}") from exc


def _question_from_mapping(question: dict[str, Any]) -> CausalQuestionSpec:
    treatment = _mapping(question, "treatment")
    outcome = _mapping(question, "outcome")
    negative_controls = _mapping(question, "negative_controls")
    dag = _mapping(question, "dag_assumptions")
    return CausalQuestionSpec(
        question_id=str(question["id"]),
        title=str(question["title"]),
        treatment_name=str(treatment["name"]),
        treatment_contrast=str(treatment["contrast"]),
        outcome_name=str(outcome["name"]),
        outcome_label_field=str(outcome["label_field"]),
        outcome_timing=str(outcome["timing"]),
        estimand=dict(_mapping(question, "estimand")),
        negative_control_outcomes=_tuple(negative_controls.get("outcomes", [])),
        negative_control_exposures=_tuple(negative_controls.get("exposures", [])),
        sensitivity_checks=_tuple(question.get("sensitivity_checks", [])),
        dag_version=str(dag["version"]),
        dag_edges=_tuple(dag.get("key_edges", [])),
        residual_risks=_tuple(dag.get("residual_risks", [])),
        predictive_separation=str(question.get("predictive_separation", "")),
    )


def _mapping(payload: dict[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"Expected `{key}` mapping in causal question registry.")
    return value


def _tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ValueError("Expected a list in causal question registry.")
    return tuple(str(item) for item in value)
