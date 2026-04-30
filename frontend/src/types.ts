export type RiskBand = 'green' | 'amber' | 'red'
export type HeatmapMode = 'delta' | 'baseline' | 'scenario'

export interface FeatureProfile {
  age: number
  bmi: number
  smoker: boolean
  alcohol_servings_per_week: number
  exercise_minutes_per_week: number
  annual_aqi: number
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
  features: FeatureDefinition[]
  organs: OrganDefinition[]
  conditions: ConditionDefinition[]
  runtime: RuntimeMetadataResponse
}

export interface RuntimeMetadataResponse {
  engine_mode: 'demo' | 'artifact'
  engine_source: 'explicit' | 'auto' | 'fallback'
  artifact_bundle_id: string | null
  message: string
}

export interface ConditionScoreResponse {
  condition_id: string
  label: string
  organ_id: string
  probability: number
  band: RiskBand
  key_drivers: string[]
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
}

export interface ScenarioCompareResponse {
  baseline: ScenarioEvaluationResponse
  candidate: ScenarioEvaluationResponse
  organ_deltas: OrganDeltaResponse[]
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
