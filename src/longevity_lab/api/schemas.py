"""API schemas shared across route modules."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

ApiContractVersion = Literal["v2"]
RiskBand = Literal["green", "amber", "red"]
ExplanationDirection = Literal["increases", "decreases", "neutral"]
ExplanationMethod = Literal["demo", "tree_path", "shap"]
UncertaintyMethod = Literal["calibration_interval"]
GeographyLevel = Literal["state", "county", "tract", "zcta"]
ScenarioGeographyLevel = Literal["state"]

API_CONTRACT_VERSION: ApiContractVersion = "v2"


def _default_supported_geography_levels() -> list[ScenarioGeographyLevel]:
    """Return state-only serving geography levels."""
    return ["state"]


class HealthResponse(BaseModel):
    """Health-check response."""

    model_config = ConfigDict(extra="forbid")

    status: str
    app_name: str
    environment: str


class FeatureProfile(BaseModel):
    """Scenario input sent from the UI."""

    model_config = ConfigDict(extra="forbid")

    age: int = Field(default=45, ge=18, le=100)
    bmi: float = Field(default=28.0, ge=10, le=60)
    smoker: bool = True
    alcohol_servings_per_week: int = Field(default=10, ge=0, le=70)
    exercise_minutes_per_week: int = Field(default=60, ge=0, le=2000)
    annual_aqi: int = Field(default=80, ge=0, le=500)
    pm25_mean: float = Field(default=9.0, ge=0, le=50)
    ozone_mean: float = Field(default=0.04, ge=0, le=0.2)


class FeatureDefinition(BaseModel):
    """Feature metadata for form generation."""

    model_config = ConfigDict(extra="forbid")

    field: str
    label: str
    kind: Literal["number", "boolean"]
    min_value: float | int | None = None
    max_value: float | int | None = None
    step: float | int | None = None


class OrganDefinitionResponse(BaseModel):
    """Organ metadata."""

    model_config = ConfigDict(extra="forbid")

    organ_id: str
    label: str
    description: str


class ConditionDefinitionResponse(BaseModel):
    """Condition metadata."""

    model_config = ConfigDict(extra="forbid")

    condition_id: str
    label: str
    organ_id: str
    description: str
    citation_label: str
    citation_url: str


class RuntimeMetadataResponse(BaseModel):
    """Runtime mode and artifact metadata shown to the frontend."""

    model_config = ConfigDict(extra="forbid")

    engine_mode: Literal["demo", "artifact"]
    engine_source: Literal["explicit", "auto", "fallback"]
    artifact_bundle_id: str | None = None
    message: str


class ContextualGeographyMetadataResponse(BaseModel):
    """Contextual geography availability in the active scoring contract."""

    model_config = ConfigDict(extra="forbid")

    available: bool
    levels: list[GeographyLevel] = Field(default_factory=list)
    source: str | None = None
    feature_count: int = 0
    features: list[str] = Field(default_factory=list)
    data_vintage: str | None = None
    caveat: str | None = None


class ModelMetadataResponse(BaseModel):
    """Versioned model/provenance metadata shared by bootstrap and scoring responses."""

    model_config = ConfigDict(extra="forbid")

    model_mode: Literal["demo", "artifact"]
    artifact_id: str | None = None
    data_vintage: str | None = None
    dataset_name: str | None = None
    dataset_version: str | None = None
    dataset_retrieved_at: str | None = None
    explanation_methods: list[ExplanationMethod]
    uncertainty_available: bool
    uncertainty_methods: list[UncertaintyMethod] = Field(default_factory=list)
    contextual_geography: ContextualGeographyMetadataResponse


class GeographyServingMetadataResponse(BaseModel):
    """Geography-selection metadata for state-year context serving."""

    model_config = ConfigDict(extra="forbid")

    supported_levels: list[ScenarioGeographyLevel] = Field(
        default_factory=_default_supported_geography_levels
    )
    default_year: int = Field(default=2023, ge=2000, le=2100)
    context_lookup_active: bool
    geographies_endpoint: str = "/api/context/geographies"
    caveat: str


class MetadataBootstrapResponse(BaseModel):
    """Bootstrap metadata for the frontend."""

    model_config = ConfigDict(extra="forbid")

    contract_version: ApiContractVersion = API_CONTRACT_VERSION
    features: list[FeatureDefinition]
    organs: list[OrganDefinitionResponse]
    conditions: list[ConditionDefinitionResponse]
    runtime: RuntimeMetadataResponse
    model_metadata: ModelMetadataResponse
    geography: GeographyServingMetadataResponse


class ExplanationRecordResponse(BaseModel):
    """Typed model-derived explanation for a condition score."""

    model_config = ConfigDict(extra="forbid")

    feature: str
    display_name: str
    direction: ExplanationDirection
    magnitude: float
    method: ExplanationMethod
    caveat: str


class UncertaintySummaryResponse(BaseModel):
    """Artifact-declared calibrated uncertainty interval."""

    model_config = ConfigDict(extra="forbid")

    method: UncertaintyMethod
    lower: float
    upper: float
    confidence_level: float | None = None
    caveat: str
    diagnostics: dict[str, float] = Field(default_factory=dict)


class ConditionScoreResponse(BaseModel):
    """Predicted condition probability."""

    model_config = ConfigDict(extra="forbid")

    condition_id: str
    label: str
    organ_id: str
    probability: float
    band: RiskBand
    key_drivers: list[str]
    explanations: list[ExplanationRecordResponse] = Field(default_factory=list)
    uncertainty: UncertaintySummaryResponse | None = None


class OrganSummaryResponse(BaseModel):
    """Aggregated organ score."""

    model_config = ConfigDict(extra="forbid")

    organ_id: str
    label: str
    score: float
    band: RiskBand
    top_conditions: list[str]


class ScenarioEvaluationResponse(BaseModel):
    """Single-scenario evaluation response."""

    model_config = ConfigDict(extra="forbid")

    summary_score: float
    organs: list[OrganSummaryResponse]
    conditions: list[ConditionScoreResponse]


class OrganDeltaResponse(BaseModel):
    """Baseline-vs-candidate delta for one organ."""

    model_config = ConfigDict(extra="forbid")

    organ_id: str
    label: str
    baseline_score: float
    candidate_score: float
    score_delta: float
    band: RiskBand
    top_conditions: list[str]


class ScenarioGeographySelection(BaseModel):
    """State-year geography context attached to a scenario comparison."""

    model_config = ConfigDict(extra="forbid")

    level: ScenarioGeographyLevel = "state"
    state_fips: str = Field(pattern=r"^\d{2}$")
    year: int = Field(default=2023, ge=2000, le=2100)


class ScenarioCompareRequest(BaseModel):
    """Compare request between baseline and candidate profiles."""

    model_config = ConfigDict(extra="forbid")

    baseline: FeatureProfile
    candidate: FeatureProfile
    geography: ScenarioGeographySelection | None = None


class ScenarioCompareResponse(BaseModel):
    """Scenario comparison response."""

    model_config = ConfigDict(extra="forbid")

    contract_version: ApiContractVersion = API_CONTRACT_VERSION
    baseline: ScenarioEvaluationResponse
    candidate: ScenarioEvaluationResponse
    organ_deltas: list[OrganDeltaResponse]
    model_metadata: ModelMetadataResponse


class ContextReadinessResponse(BaseModel):
    """Readiness metadata for local processed context lookup tables."""

    model_config = ConfigDict(extra="forbid")

    active: bool
    table_exists: bool
    year_available: bool
    table_path: str
    state_count: int
    available_years: list[int] = Field(default_factory=list)
    message: str


class StateGeographyOptionResponse(BaseModel):
    """One selectable state-year context option."""

    model_config = ConfigDict(extra="forbid")

    level: ScenarioGeographyLevel = "state"
    state_fips: str = Field(pattern=r"^\d{2}$")
    label: str
    year: int
    context_available: bool


class GeographyOptionsResponse(BaseModel):
    """State-year geography options for scenario background context."""

    model_config = ConfigDict(extra="forbid")

    contract_version: ApiContractVersion = API_CONTRACT_VERSION
    selected_year: int
    supported_levels: list[ScenarioGeographyLevel] = Field(
        default_factory=_default_supported_geography_levels
    )
    options: list[StateGeographyOptionResponse]
    readiness: ContextReadinessResponse


class PipelineArtifactStatus(BaseModel):
    """Filesystem presence/status for one expected data pipeline artifact."""

    model_config = ConfigDict(extra="forbid")

    artifact_id: str
    label: str
    path: str
    exists: bool
    bytes: int | None = None
    modified_at: str | None = None


class PipelineProvenanceSummary(BaseModel):
    """A small summary extracted from a provenance JSON file."""

    model_config = ConfigDict(extra="forbid")

    path: str
    dataset_name: str
    dataset_version: str
    retrieved_at: str
    extra: dict[str, Any] = Field(default_factory=dict)


class PipelineStatusResponse(BaseModel):
    """High-level status for raw/processed pipeline outputs for a given year."""

    model_config = ConfigDict(extra="forbid")

    year: int
    artifacts: list[PipelineArtifactStatus]
    provenance: list[PipelineProvenanceSummary]


class EvidenceSourceSummary(BaseModel):
    """A configured public source from the source registry."""

    model_config = ConfigDict(extra="forbid")

    source_id: str
    title: str
    geography: str
    expected_file_pattern: str
    local_landing_path: str
    active_in_model: bool
    role: Literal["active_model", "pipeline_context", "external_validation", "local_workflow"]
    caveat: str | None = None


class EvidenceAssetStatus(BaseModel):
    """Filesystem status for one evidence asset."""

    model_config = ConfigDict(extra="forbid")

    asset_id: str
    label: str
    kind: Literal["raw", "processed", "provenance", "duckdb", "artifact", "report"]
    path: str
    exists: bool
    bytes: int | None = None
    modified_at: str | None = None
    source_ids: list[str] = Field(default_factory=list)
    caveat: str | None = None


class EvidenceAssetGroup(BaseModel):
    """Grouped evidence assets for UI display."""

    model_config = ConfigDict(extra="forbid")

    group_id: str
    label: str
    ready_count: int
    total_count: int
    assets: list[EvidenceAssetStatus]


class EvidenceReportSummary(BaseModel):
    """Status for generated report outputs."""

    model_config = ConfigDict(extra="forbid")

    report_id: str
    label: str
    path: str
    exists: bool
    bytes: int | None = None
    modified_at: str | None = None
    caveat: str | None = None


class EvidenceProductionArtifactSummary(BaseModel):
    """Artifact deployment status without exposing release URLs."""

    model_config = ConfigDict(extra="forbid")

    active_bundle_id: str | None
    configured_bundle_id: str | None
    url_configured: bool
    sha256_configured: bool
    local_bundle_exists: bool
    release_download_configured: bool


class EvidenceFeatureInventory(BaseModel):
    """Active-vs-available feature inventory."""

    model_config = ConfigDict(extra="forbid")

    scenario_editable: list[str]
    active_model_features: list[str]
    active_model_features_by_condition: dict[str, list[str]] = Field(default_factory=dict)
    training_config_features: list[str]
    training_context_features: list[str]
    available_pipeline_context_features: list[str]
    report_only_features: list[str]


class EvidenceInactiveGap(BaseModel):
    """A known gap between implemented pipeline capability and active scoring."""

    model_config = ConfigDict(extra="forbid")

    gap_id: str
    label: str
    status: Literal["implemented_not_active", "local_only", "not_generated", "not_served"]
    evidence: list[str]
    explanation: str
    next_action: str | None = None


class EvidenceStatusResponse(BaseModel):
    """Comprehensive evidence and runtime status for the product UI."""

    model_config = ConfigDict(extra="forbid")

    contract_version: ApiContractVersion = API_CONTRACT_VERSION
    year: int
    runtime: RuntimeMetadataResponse
    model_metadata: ModelMetadataResponse
    sources: list[EvidenceSourceSummary]
    asset_groups: list[EvidenceAssetGroup]
    reports: list[EvidenceReportSummary]
    production_artifact: EvidenceProductionArtifactSummary
    feature_inventory: EvidenceFeatureInventory
    inactive_gaps: list[EvidenceInactiveGap]


class ModelMetricSetResponse(BaseModel):
    """A small set of model performance metrics."""

    model_config = ConfigDict(extra="forbid")

    average_precision: float | None = None
    roc_auc: float | None = None
    brier_score: float | None = None


class ConditionModelCardResponse(BaseModel):
    """Metrics and training metadata for one condition model."""

    model_config = ConfigDict(extra="forbid")

    condition_id: str
    label: str
    metrics_available: bool
    metrics_path: str | None = None
    rows_total: int | None = None
    rows_train: int | None = None
    rows_test: int | None = None
    positive_rate: float | None = None
    feature_count: int | None = None
    features: list[str] = Field(default_factory=list)
    context_feature_count: int = 0
    context_features: list[str] = Field(default_factory=list)
    best_params: dict[str, Any] = Field(default_factory=dict)
    base_metrics: ModelMetricSetResponse = Field(default_factory=ModelMetricSetResponse)
    calibrated_metrics: ModelMetricSetResponse = Field(default_factory=ModelMetricSetResponse)
    no_context_metrics: ModelMetricSetResponse = Field(default_factory=ModelMetricSetResponse)
    no_aqi_metrics: ModelMetricSetResponse = Field(default_factory=ModelMetricSetResponse)
    no_pollutants_metrics: ModelMetricSetResponse = Field(default_factory=ModelMetricSetResponse)
    context_average_precision_delta: float | None = None
    aqi_average_precision_delta: float | None = None
    pollutant_average_precision_delta: float | None = None
    uncertainty_method: UncertaintyMethod | None = None
    uncertainty_path: str | None = None
    uncertainty_half_width: float | None = None
    uncertainty_confidence_level: float | None = None
    uncertainty_empirical_coverage: float | None = None
    uncertainty_expected_calibration_error: float | None = None
    uncertainty_caveat: str | None = None


class ModelCardBundleResponse(BaseModel):
    """Model-card response for the active scoring bundle."""

    model_config = ConfigDict(extra="forbid")

    contract_version: ApiContractVersion = API_CONTRACT_VERSION
    model_metadata: ModelMetadataResponse
    available: bool
    message: str
    artifact_id: str | None = None
    generated_from: str | None = None
    condition_cards: list[ConditionModelCardResponse] = Field(default_factory=list)


class CommunityFeatureValueResponse(BaseModel):
    """One context or validation feature shown on the Community Context page."""

    model_config = ConfigDict(extra="forbid")

    feature: str
    label: str
    value: float | int | str | bool | None = None
    formatted_value: str
    units: str | None = None
    role: Literal["state_context", "county_context", "places_context"]
    caveat: str | None = None


class CommunityGeographyOptionResponse(BaseModel):
    """One selectable geography option for community context."""

    model_config = ConfigDict(extra="forbid")

    level: Literal["state", "county"]
    state_fips: str
    county_fips: str | None = None
    label: str
    year: int
    feature_count: int
    selected: bool = False


class CommunityGeographySummaryResponse(BaseModel):
    """Selected state or county context summary."""

    model_config = ConfigDict(extra="forbid")

    level: Literal["state", "county"]
    available: bool
    label: str | None = None
    state_fips: str | None = None
    county_fips: str | None = None
    year: int
    source_path: str | None = None
    message: str
    features: list[CommunityFeatureValueResponse] = Field(default_factory=list)
    options: list[CommunityGeographyOptionResponse] = Field(default_factory=list)
    caveat: str


class CommunityPlacesValidationRowResponse(BaseModel):
    """One model-vs-PLACES aggregate validation row."""

    model_config = ConfigDict(extra="forbid")

    condition_id: str
    geography_level: Literal["state", "county", "national"]
    geography_name: str | None = None
    state_fips: str | None = None
    county_fips: str | None = None
    model_mean_predicted_probability: float | None = None
    places_crude_prevalence_probability: float | None = None
    absolute_difference: float | None = None
    comparison_direction: str | None = None
    places_reference_kind: str | None = None


class CommunityPlacesValidationSummaryResponse(BaseModel):
    """PLACES aggregate validation summary for local report outputs."""

    model_config = ConfigDict(extra="forbid")

    available: bool
    report_path: str | None = None
    places_release_year: int
    row_count: int
    conditions_compared: list[str] = Field(default_factory=list)
    rows: list[CommunityPlacesValidationRowResponse] = Field(default_factory=list)
    caveat: str
    message: str


class CommunityCausalReportSummaryResponse(BaseModel):
    """Summary of one local causal workbench report."""

    model_config = ConfigDict(extra="forbid")

    question_id: str
    title: str
    status: str
    report_path: str
    markdown_path: str | None = None
    rows: int | None = None
    treatment: str | None = None
    outcome: str | None = None
    estimand: str | None = None
    estimate_method: str | None = None
    risk_difference: float | None = None
    diagnostic_status: str | None = None
    heterogeneity_status: str | None = None
    caveat: str


class CommunityContextOverviewResponse(BaseModel):
    """Community context and research evidence overview."""

    model_config = ConfigDict(extra="forbid")

    contract_version: ApiContractVersion = API_CONTRACT_VERSION
    year: int
    places_year: int
    state_context: CommunityGeographySummaryResponse
    county_context: CommunityGeographySummaryResponse
    places_context: CommunityGeographySummaryResponse
    places_validation: CommunityPlacesValidationSummaryResponse
    causal_reports: list[CommunityCausalReportSummaryResponse] = Field(default_factory=list)
    caveat: str
