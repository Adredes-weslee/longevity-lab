"""Tests for causal question registry loading."""

from __future__ import annotations

from longevity_lab.causal.datasets import load_causal_config_for_question
from longevity_lab.causal.registry import (
    default_config_path_for_question,
    load_question_registry,
    load_question_spec,
    resolve_question_id,
)


def test_registry_loads_all_pr11_questions() -> None:
    """The machine-readable registry should expose every PR11 causal question."""
    registry = load_question_registry()

    assert set(registry) == {
        "smoking_chronic_lung_disease",
        "physical_activity_diabetes",
        "bmi_diabetes",
        "alcohol_depression",
    }
    activity = registry["physical_activity_diabetes"]
    assert activity.treatment_name == "meets_physical_activity_guidance"
    assert activity.outcome_label_field == "label_diabetes"
    assert activity.dag_version == "activity_diabetes_v1"
    assert "dowhy_placebo_subset_random_common_cause_refutations" in (activity.sensitivity_checks)


def test_registry_aliases_map_cli_names_to_canonical_questions() -> None:
    """CLI aliases should resolve to canonical registry ids and run configs."""
    assert resolve_question_id("activity_diabetes") == "physical_activity_diabetes"
    assert load_question_spec("activity_diabetes").question_id == "physical_activity_diabetes"
    assert default_config_path_for_question("activity_diabetes").name == "activity_diabetes.yaml"


def test_concrete_run_config_uses_registry_metadata() -> None:
    """Concrete configs should get treatment, outcome, DAG, and estimand from registry."""
    config = load_causal_config_for_question("alcohol_depression")

    assert config.question_id == "alcohol_depression"
    assert config.title == "Heavy alcohol use and diagnosed depression"
    assert config.treatment_name == "heavy_alcohol_use"
    assert config.treatment_column == "heavy_alcohol_use"
    assert config.outcome_column == "label_depression"
    assert config.dag_version == "alcohol_depression_v1"
    assert config.output_dir.as_posix().endswith("data/processed/reports/causal/alcohol_depression")
