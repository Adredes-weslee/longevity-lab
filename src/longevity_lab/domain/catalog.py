"""Domain catalog definitions for organs and conditions."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class OrganDefinition:
    """Static organ metadata."""

    organ_id: str
    label: str
    description: str


@dataclass(frozen=True, slots=True)
class ConditionDefinition:
    """Condition-to-organ metadata."""

    condition_id: str
    label: str
    organ_id: str
    description: str
    citation_label: str
    citation_url: str


ORGANS: tuple[OrganDefinition, ...] = (
    OrganDefinition(
        "heart",
        "Heart",
        "Cardiovascular outcomes and lifestyle-sensitive risk signals.",
    ),
    OrganDefinition(
        "lungs",
        "Lungs",
        "Respiratory outcomes with strong smoking and air-quality effects.",
    ),
    OrganDefinition(
        "brain",
        "Brain",
        "Stroke and mental-health outcomes influenced by lifestyle factors.",
    ),
    OrganDefinition("pancreas", "Pancreas", "Metabolic outcomes such as diabetes risk."),
)


CONDITIONS: tuple[ConditionDefinition, ...] = (
    ConditionDefinition(
        "heart_disease",
        "Heart disease",
        "heart",
        "Illustrative cardiovascular outcome used in the demo scaffold.",
        "BRFSS + decision-tree baseline",
        "https://www.cdc.gov/brfss/",
    ),
    ConditionDefinition(
        "chronic_lung_disease",
        "Chronic lung disease",
        "lungs",
        "Illustrative respiratory outcome used in the demo scaffold.",
        "BRFSS + air quality context",
        "https://aqs.epa.gov/aqsweb/airdata/download_files.html#Annual",
    ),
    ConditionDefinition(
        "stroke",
        "Stroke",
        "brain",
        "Illustrative neurologic outcome used in the demo scaffold.",
        "BRFSS health-outcome labels",
        "https://www.cdc.gov/brfss/annual_data/annual_2023.html",
    ),
    ConditionDefinition(
        "depression",
        "Depression",
        "brain",
        "Illustrative mental-health outcome used in the demo scaffold.",
        "BRFSS self-report mental-health fields",
        "https://www.cdc.gov/brfss/about/index.htm",
    ),
    ConditionDefinition(
        "diabetes",
        "Diabetes",
        "pancreas",
        "Illustrative metabolic outcome used in the demo scaffold.",
        "BRFSS diabetes label",
        "https://www.cdc.gov/brfss/annual_data/annual_2023.html",
    ),
)
