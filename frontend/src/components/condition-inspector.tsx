import type { CSSProperties, JSX } from 'react'

import { healthRecommendations } from '../content/health-recommendations'
import type {
  ConditionDefinition,
  ExplanationRecordResponse,
  HeatmapMode,
  OrganDefinition,
  ScenarioCompareResponse,
  UncertaintySummaryResponse,
} from '../types'

interface ConditionInspectorProps {
  comparison: ScenarioCompareResponse | null
  conditions: ConditionDefinition[]
  mode: HeatmapMode
  organs: OrganDefinition[]
  selectedOrganId: string | null
}

function formatPercent(value: number): string {
  return `${(value * 100).toFixed(1)}%`
}

function formatDelta(value: number): string {
  return `${value >= 0 ? '+' : ''}${(value * 100).toFixed(1)}%`
}

interface RenderedCondition {
  band: 'green' | 'amber' | 'red'
  conditionId: string
  description: string
  displayValue: string
  driverLabel: string
  drivers: string[]
  explanations: ExplanationRecordResponse[]
  label: string
  style: CSSProperties
  uncertainty: UncertaintySummaryResponse | null
  valueLabel: string
  citationLabel: string
  citationUrl: string
}

interface RecommendationCondition {
  conditionId: string
  label: string
  recommendation: string
  severityScore: number
  title: string
  scoreSummary: string
  stateLabel: string
  statusMessage: string
  citations: Array<{
    title: string
    url: string
  }>
}

function formatDirection(direction: ExplanationRecordResponse['direction']): string {
  if (direction === 'increases') {
    return 'raises predicted risk'
  }
  if (direction === 'decreases') {
    return 'lowers predicted risk'
  }
  return 'is neutral in this rule path'
}

function formatUncertainty(uncertainty: UncertaintySummaryResponse): string {
  const confidence = uncertainty.confidence_level
    ? `, ${(uncertainty.confidence_level * 100).toFixed(0)}% level`
    : ''
  return `${formatPercent(uncertainty.lower)}-${formatPercent(uncertainty.upper)}${confidence}`
}

export function ConditionInspector({
  comparison,
  conditions,
  mode,
  organs,
  selectedOrganId,
}: ConditionInspectorProps): JSX.Element {
  const organ = organs.find((entry) => entry.organ_id === selectedOrganId) ?? null
  const delta = comparison?.organ_deltas.find((entry) => entry.organ_id === selectedOrganId) ?? null
  const baselineConditions = comparison?.baseline.conditions.filter(
    (entry) => entry.organ_id === selectedOrganId,
  ) ?? []
  const candidateConditions = comparison?.candidate.conditions.filter(
    (entry) => entry.organ_id === selectedOrganId,
  ) ?? []
  const activeRiskLabel =
    mode === 'baseline' ? 'Current risk' : mode === 'scenario' ? 'What-if risk' : 'Change vs current'
  const activeRiskValue =
    delta == null
      ? '--'
      : mode === 'baseline'
        ? formatPercent(delta.baseline_score)
        : mode === 'scenario'
          ? formatPercent(delta.candidate_score)
          : formatDelta(delta.score_delta)

  const renderedConditions: RenderedCondition[] =
    mode === 'baseline'
      ? baselineConditions.map((condition) => {
          const metadata = conditions.find((entry) => entry.condition_id === condition.condition_id)
          return {
            band: condition.band,
            conditionId: condition.condition_id,
            description: metadata?.description ?? 'Condition metadata not yet loaded.',
            displayValue: formatPercent(condition.probability),
            driverLabel: 'Current drivers',
            drivers: condition.key_drivers,
            explanations: condition.explanations ?? [],
            label: condition.label,
            style: { width: `${Math.max(condition.probability * 100, 3)}%` },
            uncertainty: condition.uncertainty ?? null,
            valueLabel: 'Current',
            citationLabel: metadata?.citation_label ?? '',
            citationUrl: metadata?.citation_url ?? '',
          }
        })
      : candidateConditions.map((condition) => {
          const metadata = conditions.find((entry) => entry.condition_id === condition.condition_id)
          const baseline = baselineConditions.find(
            (entry) => entry.condition_id === condition.condition_id,
          )
          const deltaValue = condition.probability - (baseline?.probability ?? 0)

          return {
            band: condition.band,
            conditionId: condition.condition_id,
            description: metadata?.description ?? 'Condition metadata not yet loaded.',
            displayValue: mode === 'scenario' ? formatPercent(condition.probability) : formatDelta(deltaValue),
            driverLabel: mode === 'scenario' ? 'What-if drivers' : 'Change drivers',
            drivers: condition.key_drivers,
            explanations: condition.explanations ?? [],
            label: condition.label,
            style: {
              width:
                mode === 'scenario'
                  ? `${Math.max(condition.probability * 100, 3)}%`
                  : `${Math.max(Math.abs(deltaValue) * 100, 3)}%`,
            },
            uncertainty: condition.uncertainty ?? null,
            valueLabel: mode === 'scenario' ? 'What-if' : 'Change',
            citationLabel: metadata?.citation_label ?? '',
            citationUrl: metadata?.citation_url ?? '',
          }
        })

  const recommendationConditions: RecommendationCondition[] = candidateConditions
    .map((candidate) => {
      const baseline = baselineConditions.find(
        (entry) => entry.condition_id === candidate.condition_id,
      )
      const guidance = healthRecommendations[candidate.condition_id]
      if (!guidance) {
        return null
      }

      const baselineProbability = baseline?.probability ?? 0
      const candidateProbability = candidate.probability
      const baselineHighRisk = baselineProbability >= 0.35
      const candidateHighRisk = candidateProbability >= 0.35

      if (!baselineHighRisk && !candidateHighRisk) {
        return null
      }

      let stateLabel = 'Guidance for what-if risk'
      let statusMessage = 'This what-if profile enters the high-risk band.'
      let scoreSummary = `What-if ${formatPercent(candidateProbability)}`

      if (baselineHighRisk && candidateHighRisk) {
        stateLabel = 'Guidance for current and what-if risk'
        scoreSummary = `Current ${formatPercent(baselineProbability)} | What-if ${formatPercent(candidateProbability)}`
        if (candidateProbability > baselineProbability + 0.005) {
          statusMessage = 'Current and what-if both remain in the high-risk band, and the scenario worsens it.'
        } else if (candidateProbability < baselineProbability - 0.005) {
          statusMessage = 'Current and what-if both remain in the high-risk band, although the scenario lowers risk.'
        } else {
          statusMessage = 'Current and what-if both remain in the high-risk band.'
        }
      } else if (baselineHighRisk) {
        stateLabel = 'Guidance for current risk'
        scoreSummary = `Current ${formatPercent(baselineProbability)}`
        statusMessage =
          candidateProbability < baselineProbability
            ? 'Current profile is high-risk; this scenario improves it.'
            : 'Current profile is in the high-risk band.'
      }

      return {
        conditionId: candidate.condition_id,
        label: candidate.label,
        recommendation: guidance.recommendation,
        severityScore: Math.max(baselineProbability, candidateProbability),
        title: guidance.title,
        scoreSummary,
        stateLabel,
        statusMessage,
        citations: guidance.citations,
      }
    })
    .filter((condition): condition is RecommendationCondition => condition !== null)
    .sort((left, right) => right.severityScore - left.severityScore)

  return (
    <section className="panel inspector-panel" data-testid="condition-inspector">
      <div className="panel-header">
        <h2>Drill-down</h2>
        <p>Compare current vs what-if risk and inspect the main model-derived drivers.</p>
      </div>

      {!organ || !delta ? (
        <p className="muted">Select an organ to inspect its condition breakdown.</p>
      ) : (
        <>
          <div className="inspector-summary">
            <div>
              <h3>{organ.label}</h3>
              <p>{organ.description}</p>
            </div>
            <div className="inspector-score-card">
              <span>{activeRiskLabel}</span>
              <strong>{activeRiskValue}</strong>
            </div>
          </div>

          <div className="delta-strip">
            <div>
              <span>Current</span>
              <strong>{formatPercent(delta.baseline_score)}</strong>
            </div>
            <div>
              <span>What-if</span>
              <strong>{formatPercent(delta.candidate_score)}</strong>
            </div>
            <div>
              <span>Change</span>
              <strong>{formatDelta(delta.score_delta)}</strong>
            </div>
          </div>

          {recommendationConditions.length ? (
            <section className="recommendation-panel" data-testid="health-guidance">
              <div className="panel-header">
                <h3>What may help</h3>
                <p>
                  The CDC links below are general public-health guidance, not personal medical
                  advice.
                </p>
              </div>
              <ul className="recommendation-list">
                {recommendationConditions.map((condition) => {
                  return (
                    <li className="recommendation-card" key={`recommendation-${condition.conditionId}`}>
                      <div className="recommendation-card-header">
                        <div>
                          <h4>{condition.label}</h4>
                          <p className="recommendation-title">{condition.stateLabel}</p>
                        </div>
                      </div>
                      <strong className="recommendation-score">{condition.scoreSummary}</strong>
                      <p className="recommendation-status">{condition.statusMessage}</p>
                      <p className="recommendation-copy">{condition.recommendation}</p>
                      <div className="recommendation-links">
                        {condition.citations.map((citation) => (
                          <a
                            className="citation-link recommendation-link"
                            href={citation.url}
                            key={`${condition.conditionId}-${citation.url}`}
                            rel="noreferrer"
                            target="_blank"
                          >
                            {citation.title}
                          </a>
                        ))}
                      </div>
                    </li>
                  )
                })}
              </ul>
            </section>
          ) : null}

          <ul className="condition-list">
            {renderedConditions.map((condition) => {
              return (
                <li
                  className={`condition-card band-${condition.band}`}
                  data-testid={`condition-${condition.conditionId}`}
                  key={condition.conditionId}
                >
                  <div className="condition-card-header">
                    <div>
                      <h4>{condition.label}</h4>
                      <p className="condition-description">
                        {condition.description}
                      </p>
                    </div>
                    <div className="condition-value-block">
                      <span>{condition.valueLabel}</span>
                      <strong>{condition.displayValue}</strong>
                    </div>
                  </div>
                  <div className="condition-bar-track" aria-hidden="true">
                    <div
                      className="condition-bar-fill"
                      style={condition.style}
                    />
                  </div>
                  <p className="condition-driver-label">{condition.driverLabel}</p>
                  <div className="driver-list">
                    {condition.drivers.length ? (
                      condition.drivers.map((driver) => (
                        <span className="driver-chip" key={`${condition.conditionId}-${driver}`}>
                          {driver}
                        </span>
                      ))
                    ) : (
                      <span className="muted">No drivers available.</span>
                    )}
                  </div>
                  <div className="explanation-block">
                    <p className="condition-driver-label">Model explanation caveats</p>
                    {condition.explanations.length ? (
                      <ul className="explanation-list">
                        {condition.explanations.map((explanation) => (
                          <li key={`${condition.conditionId}-${explanation.feature}-${explanation.method}`}>
                            <strong>{explanation.display_name}</strong>
                            <span>{formatDirection(explanation.direction)}</span>
                            <small>{explanation.caveat}</small>
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <p className="muted explanation-empty">
                        No typed explanation is available for this condition in the active model
                        bundle.
                      </p>
                    )}
                    {condition.uncertainty ? (
                      <p className="uncertainty-note">
                        Calibrated uncertainty: {formatUncertainty(condition.uncertainty)}.
                        {' '}
                        {condition.uncertainty.caveat}
                      </p>
                    ) : (
                      <p className="uncertainty-note">
                        No calibrated uncertainty interval is declared for this condition.
                      </p>
                    )}
                  </div>
                  {condition.citationUrl ? (
                    <a className="citation-link" href={condition.citationUrl} rel="noreferrer" target="_blank">
                      {condition.citationLabel}
                    </a>
                  ) : null}
                </li>
              )
            })}
          </ul>
        </>
      )}
    </section>
  )
}
