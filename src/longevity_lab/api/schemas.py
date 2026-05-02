"""API schemas shared across route modules."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

ApiContractVersion = Literal["v2"]
RiskBand = Literal["green", "amber", "red"]
ExplanationDirection = Literal["increases", "decreases", "neutral"]
ExplanationMethod = Literal["demo", "tree_path", "shap"]
UncertaintyMethod = Literal["calibration_interval"]
GeographyLevel = Literal["state", "county", "tract", "zcta"]

API_CONTRACT_VERSION: ApiContractVersion = "v2"


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


class MetadataBootstrapResponse(BaseModel):
    """Bootstrap metadata for the frontend."""

    model_config = ConfigDict(extra="forbid")

    contract_version: ApiContractVersion = API_CONTRACT_VERSION
    features: list[FeatureDefinition]
    organs: list[OrganDefinitionResponse]
    conditions: list[ConditionDefinitionResponse]
    runtime: RuntimeMetadataResponse
    model_metadata: ModelMetadataResponse


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


class ScenarioCompareRequest(BaseModel):
    """Compare request between baseline and candidate profiles."""

    model_config = ConfigDict(extra="forbid")

    baseline: FeatureProfile
    candidate: FeatureProfile


class ScenarioCompareResponse(BaseModel):
    """Scenario comparison response."""

    model_config = ConfigDict(extra="forbid")

    contract_version: ApiContractVersion = API_CONTRACT_VERSION
    baseline: ScenarioEvaluationResponse
    candidate: ScenarioEvaluationResponse
    organ_deltas: list[OrganDeltaResponse]
    model_metadata: ModelMetadataResponse


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
    best_params: dict[str, Any] = Field(default_factory=dict)
    base_metrics: ModelMetricSetResponse = Field(default_factory=ModelMetricSetResponse)
    calibrated_metrics: ModelMetricSetResponse = Field(default_factory=ModelMetricSetResponse)
    no_aqi_metrics: ModelMetricSetResponse = Field(default_factory=ModelMetricSetResponse)
    aqi_average_precision_delta: float | None = None


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
