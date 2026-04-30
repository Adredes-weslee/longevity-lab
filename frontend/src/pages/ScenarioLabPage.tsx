import type { JSX } from 'react'

import { useScenario } from '../state/scenario-context'
import type {
  FeatureProfile,
  ScenarioCompareResponse,
} from '../types'

interface ScenarioLabPageProps {
  comparison: ScenarioCompareResponse | null
  loading: boolean
}

const featureLabels: Record<keyof FeatureProfile, string> = {
  age: 'Age',
  bmi: 'BMI',
  smoker: 'Smoking',
  alcohol_servings_per_week: 'Alcohol servings / week',
  exercise_minutes_per_week: 'Exercise minutes / week',
  annual_aqi: 'Annual AQI',
}

function formatFeatureValue(field: keyof FeatureProfile, value: FeatureProfile[keyof FeatureProfile]): string {
  if (field === 'smoker') {
    return value ? 'Yes' : 'No'
  }
  if (field === 'bmi') {
    return Number(value).toFixed(1)
  }
  return String(value)
}

function changedRows(baseline: FeatureProfile, candidate: FeatureProfile): Array<{
  field: keyof FeatureProfile
  current: string
  candidate: string
}> {
  const rows: Array<{
    field: keyof FeatureProfile
    current: string
    candidate: string
  }> = []
  for (const field of Object.keys(baseline) as Array<keyof FeatureProfile>) {
    if (baseline[field] !== candidate[field]) {
      rows.push({
        field,
        current: formatFeatureValue(field, baseline[field]),
        candidate: formatFeatureValue(field, candidate[field]),
      })
    }
  }
  return rows
}

function formatPercent(value: number): string {
  return `${(value * 100).toFixed(1)}%`
}

export function ScenarioLabPage({
  comparison,
  loading,
}: ScenarioLabPageProps): JSX.Element {
  const { state } = useScenario()
  const rows = changedRows(state.baseline, state.candidate)
  const sortedDeltas = [...(comparison?.organ_deltas ?? [])].sort(
    (left, right) => Math.abs(right.score_delta) - Math.abs(left.score_delta),
  )

  return (
    <section className="page-stack" data-testid="scenario-lab-page">
      <section className="panel page-hero">
        <div className="panel-header">
          <p className="section-kicker">Scenario lab</p>
          <h2>Current what-if comparison</h2>
          <p>
            This page turns the live Explorer state into an audit-friendly scenario summary. It
            does not claim causality; it summarizes the predictive comparison returned by the API.
          </p>
        </div>
        <div className="page-stat-grid">
          <div className="page-stat">
            <span>Current score</span>
            <strong>{comparison ? comparison.baseline.summary_score.toFixed(1) : '--'}</strong>
          </div>
          <div className="page-stat">
            <span>What-if score</span>
            <strong>{comparison ? comparison.candidate.summary_score.toFixed(1) : '--'}</strong>
          </div>
          <div className="page-stat">
            <span>Changed inputs</span>
            <strong>{rows.length}</strong>
          </div>
        </div>
      </section>

      <section className="page-card-grid">
        <article className="panel info-card">
          <div className="panel-header">
            <h3>Input changes</h3>
            <p>Fields that differ between the current and what-if profile.</p>
          </div>
          {rows.length ? (
            <ul className="comparison-list">
              {rows.map((row) => (
                <li key={row.field}>
                  <span>{featureLabels[row.field]}</span>
                  <strong>
                    {row.current} → {row.candidate}
                  </strong>
                </li>
              ))}
            </ul>
          ) : (
            <p className="muted">No inputs differ yet.</p>
          )}
        </article>

        <article className="panel info-card">
          <div className="panel-header">
            <h3>Organ deltas</h3>
            <p>Largest absolute changes from the current scenario comparison.</p>
          </div>
          {comparison ? (
            <ul className="comparison-list">
              {sortedDeltas.map((delta) => (
                <li key={delta.organ_id}>
                  <span>{delta.label}</span>
                  <strong>
                    {formatPercent(delta.baseline_score)} → {formatPercent(delta.candidate_score)}
                  </strong>
                </li>
              ))}
            </ul>
          ) : (
            <p className="muted">
              {loading ? 'Loading scenario comparison...' : 'Scenario comparison not loaded yet.'}
            </p>
          )}
        </article>
      </section>
    </section>
  )
}
