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
    OrganDefinition("kidneys", "Kidneys", "Kidney-function outcomes and metabolic risk signals."),
    OrganDefinition(
        "brain",
        "Brain",
        "Stroke and mental-health outcomes influenced by lifestyle factors.",
    ),
    OrganDefinition("pancreas", "Pancreas", "Metabolic outcomes such as diabetes risk."),
    OrganDefinition(
        "joints",
        "Joints",
        "Musculoskeletal outcomes linked with age, activity, and weight.",
    ),
)


CONDITIONS: tuple[ConditionDefinition, ...] = (
    ConditionDefinition(
        "heart_disease",
        "Heart disease",
        "heart",
        "BRFSS-derived cardiovascular outcome scored by the active model bundle.",
        "BRFSS + decision-tree baseline",
        "https://www.cdc.gov/brfss/",
    ),
    ConditionDefinition(
        "chronic_lung_disease",
        "Chronic lung disease",
        "lungs",
        "BRFSS-derived COPD/chronic lung disease outcome scored by the active model bundle.",
        "BRFSS + air quality context",
        "https://aqs.epa.gov/aqsweb/airdata/download_files.html#Annual",
    ),
    ConditionDefinition(
        "asthma",
        "Asthma",
        "lungs",
        "BRFSS-derived current asthma outcome scored by the active model bundle.",
        "BRFSS asthma labels + EPA pollutant context",
        "https://www.cdc.gov/asthma/",
    ),
    ConditionDefinition(
        "stroke",
        "Stroke",
        "brain",
        "BRFSS-derived stroke outcome scored by the active model bundle.",
        "BRFSS health-outcome labels",
        "https://www.cdc.gov/brfss/annual_data/annual_2023.html",
    ),
    ConditionDefinition(
        "depression",
        "Depression",
        "brain",
        "BRFSS-derived depression outcome scored by the active model bundle.",
        "BRFSS self-report mental-health fields",
        "https://www.cdc.gov/brfss/about/index.htm",
    ),
    ConditionDefinition(
        "diabetes",
        "Diabetes",
        "pancreas",
        "BRFSS-derived diabetes outcome scored by the active model bundle.",
        "BRFSS diabetes label",
        "https://www.cdc.gov/brfss/annual_data/annual_2023.html",
    ),
    ConditionDefinition(
        "kidney_disease",
        "Chronic kidney disease",
        "kidneys",
        "BRFSS-derived chronic kidney disease outcome scored by the active model bundle.",
        "BRFSS kidney disease label",
        "https://www.cdc.gov/kidney-disease/",
    ),
    ConditionDefinition(
        "arthritis",
        "Arthritis",
        "joints",
        "BRFSS-derived arthritis outcome scored by the active model bundle.",
        "BRFSS arthritis label",
        "https://www.cdc.gov/arthritis/",
    ),
)
