import { useMemo, type JSX } from 'react'

import { BodyHeatmap } from '../components/body-heatmap'
import { ConditionInspector } from '../components/condition-inspector'
import { ScenarioForm } from '../components/scenario-form'
import { disclaimers } from '../content/disclaimers'
import { useScenario } from '../state/scenario-context'
import type {
  FeatureProfile,
  HeatmapMode,
  GeographyOptionsResponse,
  MetadataBootstrapResponse,
  StateGeographyOptionResponse,
  ScenarioCompareResponse,
} from '../types'

interface ExplorerPageProps {
  bootstrap: MetadataBootstrapResponse
  busy: boolean
  comparison: ScenarioCompareResponse | null
  explanationMessage: string | null
  explanationsBusy: boolean
  geographies: GeographyOptionsResponse | null
  geographiesLoading: boolean
  geographiesError: string | null
  heatmapMode: HeatmapMode
  onChangeHeatmapMode: (mode: HeatmapMode) => void
}

function changedFeatureCount(
  baseline: FeatureProfile,
  candidate: FeatureProfile,
): number {
  let count = 0
  for (const field of Object.keys(baseline) as Array<keyof FeatureProfile>) {
    if (baseline[field] !== candidate[field]) {
      count += 1
    }
  }
  return count
}

function formatContractMetadata(metadata: MetadataBootstrapResponse): string {
  const model = metadata.model_metadata
  const dataVintage = model.data_vintage ?? 'not declared'
  const explanationMethods = model.explanation_methods.length
    ? model.explanation_methods.join(', ')
    : 'none declared'
  const uncertainty = model.uncertainty_available
    ? `uncertainty: ${model.uncertainty_methods.join(', ')}`
    : 'uncertainty: unavailable'
  const geography = model.contextual_geography.available
    ? `geography: ${model.contextual_geography.levels.join(', ')}`
    : 'geography: none'

  return `API ${metadata.contract_version}; data vintage ${dataVintage}; explanations: ${explanationMethods}; ${uncertainty}; ${geography}.`
}

function selectedStateOption(
  geographyOptions: GeographyOptionsResponse | null,
  stateFips: string | null,
): StateGeographyOptionResponse | null {
  if (!stateFips) {
    return null
  }
  return geographyOptions?.options.find((option) => option.state_fips === stateFips) ?? null
}

function ContextTransparencyCard({
  bootstrap,
  geographies,
  geographiesError,
}: {
  bootstrap: MetadataBootstrapResponse
  geographies: GeographyOptionsResponse | null
  geographiesError: string | null
}): JSX.Element {
  const { state } = useScenario()
  const selectedOption = selectedStateOption(geographies, state.geography?.state_fips ?? null)
  const context = bootstrap.model_metadata.contextual_geography
  const modelStatus = context.available
    ? 'Active in artifact scoring'
    : 'Inactive for scoring'
  const lookupStatus = geographiesError
    ? geographiesError
    : geographies?.readiness.message ?? bootstrap.geography.caveat
  const contextFeatures = context.features.slice(0, 6)

  return (
    <section className="panel context-transparency-card" data-testid="context-transparency-card">
      <div className="panel-header compact">
        <p className="section-kicker">Context transparency</p>
        <h2>State-year context status</h2>
        <p>
          Personal scenario edits stay in the current and what-if profiles. State context is
          joined as background geography metadata only when the active artifact declares it.
        </p>
      </div>
      <dl className="metadata-list compact-metadata-list">
        <div>
          <dt>Selected state/year</dt>
          <dd>
            {selectedOption
              ? `${selectedOption.label} (${selectedOption.year})`
              : 'No state selected'}
          </dd>
        </div>
        <div>
          <dt>Model use</dt>
          <dd>{modelStatus}</dd>
        </div>
        <div>
          <dt>Lookup readiness</dt>
          <dd>
            {geographies?.readiness.active
              ? 'State-year lookup ready'
              : 'State-year lookup inactive'}
          </dd>
        </div>
        <div>
          <dt>Context vintage</dt>
          <dd>{context.available ? context.data_vintage ?? 'Not declared' : 'n/a'}</dd>
        </div>
        <div>
          <dt>Context features</dt>
          <dd>
            {context.available
              ? `${context.feature_count} declared`
              : '0 active'}
          </dd>
        </div>
      </dl>
      {contextFeatures.length ? (
        <div className="driver-list" aria-label="Active context features">
          {contextFeatures.map((feature) => (
            <span className="driver-chip" key={feature}>{feature}</span>
          ))}
          {context.feature_count > contextFeatures.length ? (
            <span className="driver-chip">+{context.feature_count - contextFeatures.length} more</span>
          ) : null}
        </div>
      ) : null}
      <p className="muted">Lookup status: {lookupStatus}</p>
      {context.caveat ? <p className="muted">Model caveat: {context.caveat}</p> : null}
    </section>
  )
}

export function ExplorerPage({
  bootstrap,
  busy,
  comparison,
  explanationMessage,
  explanationsBusy,
  geographies,
  geographiesLoading,
  geographiesError,
  heatmapMode,
  onChangeHeatmapMode,
}: ExplorerPageProps): JSX.Element {
  const { state, dispatch } = useScenario()
  const scenarioRisk = comparison?.candidate.summary_score ?? null
  const baselineRisk = comparison?.baseline.summary_score ?? null
  const riskDelta =
    scenarioRisk != null && baselineRisk != null ? scenarioRisk - baselineRisk : null
  const highlightedOrgans = useMemo(() => {
    if (!comparison) {
      return []
    }
    return [...comparison.candidate.organs]
      .sort((left, right) => right.score - left.score)
      .slice(0, 4)
  }, [comparison])
  const activeChangeCount = changedFeatureCount(state.baseline, state.candidate)

  return (
    <>
      <section
        className={`runtime-banner ${bootstrap.runtime.engine_mode}`}
        data-testid="runtime-banner"
      >
        <span>
          {bootstrap.runtime.engine_mode === 'artifact'
            ? 'Artifact-backed scoring'
            : 'Demo scoring'}
        </span>
        <p>
          {bootstrap.runtime.message}
          {bootstrap.runtime.artifact_bundle_id
            ? ` Bundle: ${bootstrap.runtime.artifact_bundle_id}.`
            : ''}
        </p>
        <p className="runtime-contract" data-testid="contract-metadata">
          {formatContractMetadata(bootstrap)}
        </p>
      </section>

      <section className="overview-strip">
        <section className="overview-card primary" data-testid="overview-whatif">
          <p className="section-kicker">What-if score</p>
          <strong className="metric-value">
            {scenarioRisk != null ? scenarioRisk.toFixed(1) : '--'}
          </strong>
          <p className="metric-copy" aria-live="polite">
            {busy
              ? 'Refreshing from the latest slider positions...'
              : baselineRisk != null && riskDelta != null
              ? `Current ${baselineRisk.toFixed(1)} | ${riskDelta >= 0 ? '+' : ''}${riskDelta.toFixed(1)} vs current`
              : 'Move either profile to update the score live.'}
          </p>
        </section>
        <section className="overview-card" data-testid="overview-regions">
          <p className="section-kicker">Most affected regions</p>
          <div className="chip-row">
            {highlightedOrgans.length ? (
              highlightedOrgans.map((organ) => (
                <button
                  className="impact-chip"
                  key={organ.organ_id}
                  onClick={() => dispatch({ type: 'selectOrgan', organId: organ.organ_id })}
                  type="button"
                >
                  {organ.label}
                </button>
              ))
            ) : (
              <span className="muted">No organ scores yet.</span>
            )}
          </div>
        </section>
        <section className="overview-card" data-testid="overview-changes">
          <p className="section-kicker">Changed inputs</p>
          <strong className="metric-value small">{activeChangeCount}</strong>
          <p className="metric-copy">Lifestyle fields differ between current and what-if.</p>
        </section>
      </section>

      <section className="explorer-layout">
        <div className="explorer-side-column">
          <section className="panel explorer-disclaimer" data-testid="explorer-disclaimer">
            <div className="panel-header compact">
              <h2>{disclaimers.prediction.title}</h2>
              <p>{disclaimers.prediction.body}</p>
              <p>{disclaimers.context.body}</p>
            </div>
          </section>

          <ContextTransparencyCard
            bootstrap={bootstrap}
            geographies={geographies}
            geographiesError={geographiesError}
          />

          <ScenarioForm
            busy={busy}
            features={bootstrap.features}
            geographyError={geographiesError}
            geographyLoading={geographiesLoading}
            geographyOptions={geographies}
          />
        </div>

        <div className="explorer-main">
          <BodyHeatmap
            comparison={comparison}
            mode={heatmapMode}
            onChangeMode={onChangeHeatmapMode}
            onSelectOrgan={(organId) => dispatch({ type: 'selectOrgan', organId })}
            organs={bootstrap.organs}
            selectedOrganId={state.selectedOrganId}
          />
        </div>

        <ConditionInspector
          comparison={comparison}
          conditions={bootstrap.conditions}
          explanationMessage={explanationMessage}
          explanationsBusy={explanationsBusy}
          mode={heatmapMode}
          organs={bootstrap.organs}
          selectedOrganId={state.selectedOrganId}
        />
      </section>
    </>
  )
}
