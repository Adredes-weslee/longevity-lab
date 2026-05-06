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
  ScenarioCompareResponse,
} from '../types'

interface ExplorerPageProps {
  bootstrap: MetadataBootstrapResponse
  busy: boolean
  comparison: ScenarioCompareResponse | null
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

export function ExplorerPage({
  bootstrap,
  busy,
  comparison,
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
          <p className="metric-copy">
            {baselineRisk != null && riskDelta != null
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
          mode={heatmapMode}
          organs={bootstrap.organs}
          selectedOrganId={state.selectedOrganId}
        />
      </section>
    </>
  )
}
