export type RiskBand = 'green' | 'amber' | 'red'
export type ApiContractVersion = 'v2'
export type HeatmapMode = 'delta' | 'baseline' | 'scenario'
export type ExplanationDirection = 'increases' | 'decreases' | 'neutral'
export type ExplanationMethod = 'demo' | 'tree_path' | 'shap'
export type UncertaintyMethod = 'calibration_interval'
export type GeographyLevel = 'state' | 'county' | 'tract' | 'zcta'
export type ScenarioGeographyLevel = 'state'

export interface FeatureProfile {
  age: number
  bmi: number
  smoker: boolean
  alcohol_servings_per_week: number
  exercise_minutes_per_week: number
  annual_aqi: number
  pm25_mean: number
  ozone_mean: number
}

export interface FeatureDefinition {
  field: keyof FeatureProfile
  label: string
  kind: 'number' | 'boolean'
  min_value: number | null
  max_value: number | null
  step: number | null
}

export interface OrganDefinition {
  organ_id: string
  label: string
  description: string
}

export interface ConditionDefinition {
  condition_id: string
  label: string
  organ_id: string
  description: string
  citation_label: string
  citation_url: string
}

export interface MetadataBootstrapResponse {
  contract_version: ApiContractVersion
  features: FeatureDefinition[]
  organs: OrganDefinition[]
  conditions: ConditionDefinition[]
  runtime: RuntimeMetadataResponse
  model_metadata: ModelMetadataResponse
  geography: GeographyServingMetadataResponse
}

export interface RuntimeMetadataResponse {
  engine_mode: 'demo' | 'artifact'
  engine_source: 'explicit' | 'auto' | 'fallback'
  artifact_bundle_id: string | null
  message: string
}

export interface ContextualGeographyMetadataResponse {
  available: boolean
  levels: GeographyLevel[]
  source: string | null
}

export interface ModelMetadataResponse {
  model_mode: 'demo' | 'artifact'
  artifact_id: string | null
  data_vintage: string | null
  dataset_name: string | null
  dataset_version: string | null
  dataset_retrieved_at: string | null
  explanation_methods: ExplanationMethod[]
  uncertainty_available: boolean
  uncertainty_methods: UncertaintyMethod[]
  contextual_geography: ContextualGeographyMetadataResponse
}

export interface GeographyServingMetadataResponse {
  supported_levels: ScenarioGeographyLevel[]
  default_year: number
  context_lookup_active: boolean
  geographies_endpoint: string
  caveat: string
}

export interface ModelMetricSetResponse {
  average_precision: number | null
  roc_auc: number | null
  brier_score: number | null
}

export interface ConditionModelCardResponse {
  condition_id: string
  label: string
  metrics_available: boolean
  metrics_path: string | null
  rows_total: number | null
  rows_train: number | null
  rows_test: number | null
  positive_rate: number | null
  feature_count: number | null
  features: string[]
  best_params: Record<string, unknown>
  base_metrics: ModelMetricSetResponse
  calibrated_metrics: ModelMetricSetResponse
  no_aqi_metrics: ModelMetricSetResponse
  no_pollutants_metrics: ModelMetricSetResponse
  aqi_average_precision_delta: number | null
  pollutant_average_precision_delta: number | null
}

export interface ModelCardBundleResponse {
  contract_version: ApiContractVersion
  model_metadata: ModelMetadataResponse
  available: boolean
  message: string
  artifact_id: string | null
  generated_from: string | null
  condition_cards: ConditionModelCardResponse[]
}

export interface ConditionScoreResponse {
  condition_id: string
  label: string
  organ_id: string
  probability: number
  band: RiskBand
  key_drivers: string[]
  explanations: ExplanationRecordResponse[]
  uncertainty: UncertaintySummaryResponse | null
}

export interface ExplanationRecordResponse {
  feature: string
  display_name: string
  direction: ExplanationDirection
  magnitude: number
  method: ExplanationMethod
  caveat: string
}

export interface UncertaintySummaryResponse {
  method: UncertaintyMethod
  lower: number
  upper: number
  confidence_level: number | null
  caveat: string
}

export interface OrganSummaryResponse {
  organ_id: string
  label: string
  score: number
  band: RiskBand
  top_conditions: string[]
}

export interface ScenarioEvaluationResponse {
  summary_score: number
  organs: OrganSummaryResponse[]
  conditions: ConditionScoreResponse[]
}

export interface OrganDeltaResponse {
  organ_id: string
  label: string
  baseline_score: number
  candidate_score: number
  score_delta: number
  band: RiskBand
  top_conditions: string[]
}

export interface ScenarioCompareRequest {
  baseline: FeatureProfile
  candidate: FeatureProfile
  geography?: ScenarioGeographySelection | null
}

export interface ScenarioCompareResponse {
  contract_version: ApiContractVersion
  baseline: ScenarioEvaluationResponse
  candidate: ScenarioEvaluationResponse
  organ_deltas: OrganDeltaResponse[]
  model_metadata: ModelMetadataResponse
}

export interface ScenarioGeographySelection {
  level: ScenarioGeographyLevel
  state_fips: string
  year: number
}

export interface ContextReadinessResponse {
  active: boolean
  table_exists: boolean
  year_available: boolean
  table_path: string
  state_count: number
  available_years: number[]
  message: string
}

export interface StateGeographyOptionResponse {
  level: ScenarioGeographyLevel
  state_fips: string
  label: string
  year: number
  context_available: boolean
}

export interface GeographyOptionsResponse {
  contract_version: ApiContractVersion
  selected_year: number
  supported_levels: ScenarioGeographyLevel[]
  options: StateGeographyOptionResponse[]
  readiness: ContextReadinessResponse
}

export interface PipelineArtifactStatus {
  artifact_id: string
  label: string
  path: string
  exists: boolean
  bytes: number | null
  modified_at: string | null
}

export interface PipelineProvenanceSummary {
  path: string
  dataset_name: string
  dataset_version: string
  retrieved_at: string
  extra: Record<string, unknown>
}

export interface PipelineStatusResponse {
  year: number
  artifacts: PipelineArtifactStatus[]
  provenance: PipelineProvenanceSummary[]
}

export interface EvidenceSourceSummary {
  source_id: string
  title: string
  geography: string
  expected_file_pattern: string
  local_landing_path: string
  active_in_model: boolean
  role: 'active_model' | 'pipeline_context' | 'external_validation' | 'local_workflow'
  caveat: string | null
}

export interface EvidenceAssetStatus {
  asset_id: string
  label: string
  kind: 'raw' | 'processed' | 'provenance' | 'duckdb' | 'artifact' | 'report'
  path: string
  exists: boolean
  bytes: number | null
  modified_at: string | null
  source_ids: string[]
  caveat: string | null
}

export interface EvidenceAssetGroup {
  group_id: string
  label: string
  ready_count: number
  total_count: number
  assets: EvidenceAssetStatus[]
}

export interface EvidenceReportSummary {
  report_id: string
  label: string
  path: string
  exists: boolean
  bytes: number | null
  modified_at: string | null
  caveat: string | null
}

export interface EvidenceProductionArtifactSummary {
  active_bundle_id: string | null
  configured_bundle_id: string | null
  url_configured: boolean
  sha256_configured: boolean
  local_bundle_exists: boolean
  release_download_configured: boolean
}

export interface EvidenceFeatureInventory {
  scenario_editable: string[]
  active_model_features: string[]
  active_model_features_by_condition: Record<string, string[]>
  training_config_features: string[]
  training_context_features: string[]
  available_pipeline_context_features: string[]
  report_only_features: string[]
}

export interface EvidenceInactiveGap {
  gap_id: string
  label: string
  status: 'implemented_not_active' | 'local_only' | 'not_generated' | 'not_served'
  evidence: string[]
  explanation: string
  next_action: string | null
}

export interface EvidenceStatusResponse {
  contract_version: ApiContractVersion
  year: number
  runtime: RuntimeMetadataResponse
  model_metadata: ModelMetadataResponse
  sources: EvidenceSourceSummary[]
  asset_groups: EvidenceAssetGroup[]
  reports: EvidenceReportSummary[]
  production_artifact: EvidenceProductionArtifactSummary
  feature_inventory: EvidenceFeatureInventory
  inactive_gaps: EvidenceInactiveGap[]
}
