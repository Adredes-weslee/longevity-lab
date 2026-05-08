import type { JSX } from 'react'

import { disclaimers } from '../content/disclaimers'
import type {
  CommunityCausalReportSummaryResponse,
  CommunityContextOverviewResponse,
  CommunityFeatureValueResponse,
  CommunityGeographySummaryResponse,
  CommunityPlacesValidationRowResponse,
} from '../types'

interface CommunityContextPageProps {
  error: string | null
  loading: boolean
  onSelectCounty: (countyFips: string | null) => void
  onSelectState: (stateFips: string | null) => void
  onRetry: () => void
  overview: CommunityContextOverviewResponse | null
}

function formatPercent(value: number | null): string {
  return value == null ? '--' : `${(value * 100).toFixed(1)}%`
}

function formatSignedPercent(value: number | null): string {
  if (value == null) {
    return '--'
  }
  const sign = value > 0 ? '+' : ''
  return `${sign}${(value * 100).toFixed(1)} pp`
}

function AvailabilityPill({ available }: { available: boolean }): JSX.Element {
  return (
    <span className={available ? 'status-pill status-pill-ok' : 'status-pill status-pill-missing'}>
      {available ? 'Available' : 'Missing'}
    </span>
  )
}

function FeatureList({ features }: { features: CommunityFeatureValueResponse[] }): JSX.Element {
  if (!features.length) {
    return <p className="muted">No feature values are available for this selection.</p>
  }
  return (
    <ul className="comparison-list compact-list">
      {features.slice(0, 8).map((feature) => (
        <li key={feature.feature}>
          <span>{feature.label}</span>
          <strong>{feature.formatted_value}</strong>
        </li>
      ))}
    </ul>
  )
}

function ContextCard({
  title,
  summary,
}: {
  title: string
  summary: CommunityGeographySummaryResponse
}): JSX.Element {
  return (
    <article className="panel info-card" data-testid={`community-${summary.level}-${title.toLowerCase().replaceAll(' ', '-')}`}>
      <div className="panel-header compact">
        <p className="section-kicker">{summary.level} context</p>
        <h3>{title}</h3>
        <p>{summary.message}</p>
      </div>
      <div className="community-card-heading">
        <strong>{summary.label ?? 'No geography selected'}</strong>
        <AvailabilityPill available={summary.available} />
      </div>
      <dl className="metadata-list compact-metadata-list">
        <div>
          <dt>Year</dt>
          <dd>{summary.year}</dd>
        </div>
        <div>
          <dt>Source</dt>
          <dd>{summary.source_path ?? 'No local source file'}</dd>
        </div>
      </dl>
      <FeatureList features={summary.features} />
      <p className="muted">{summary.caveat}</p>
    </article>
  )
}

function StateContextMap({
  onSelectState,
  overview,
}: {
  onSelectState: (stateFips: string) => void
  overview: CommunityContextOverviewResponse
}): JSX.Element {
  const options = overview.state_context.options
  if (!options.length) {
    return (
      <section className="panel">
        <div className="panel-header">
          <h3>State context map</h3>
          <p>No local state context rows are available to map in this runtime.</p>
        </div>
      </section>
    )
  }
  return (
    <section className="panel" data-testid="community-state-map">
      <div className="panel-header">
        <h3>State context map</h3>
        <p>
          Tile map of available state-year context rows. Highlighting indicates the currently
          selected geography; these values are background context, not personal inputs.
        </p>
      </div>
      <div className="state-tile-map" aria-label="Available state context rows">
        {options.slice(0, 64).map((option) => (
          <button
            aria-pressed={option.selected}
            className={option.selected ? 'state-tile selected' : 'state-tile'}
            key={option.state_fips}
            onClick={() => onSelectState(option.state_fips)}
            type="button"
          >
            <span>{option.state_fips}</span>
            <strong>{option.label}</strong>
            <small>{option.feature_count} features</small>
          </button>
        ))}
      </div>
    </section>
  )
}

function GeographySelectors({
  onSelectCounty,
  onSelectState,
  overview,
}: {
  onSelectCounty: (countyFips: string | null) => void
  onSelectState: (stateFips: string | null) => void
  overview: CommunityContextOverviewResponse
}): JSX.Element {
  return (
    <section className="panel" data-testid="community-geography-selector">
      <div className="panel-header">
        <h3>Geography selector</h3>
        <p>
          Choose a state and county to inspect aggregate background context. Selection here is
          evidence-only and does not change Explorer scenario inputs.
        </p>
      </div>
      <div className="community-selector-grid">
        <label>
          <span>State context</span>
          <select
            onChange={(event) => onSelectState(event.target.value || null)}
            value={overview.state_context.state_fips ?? ''}
          >
            {overview.state_context.options.length ? null : <option value="">No states</option>}
            {overview.state_context.options.map((option) => (
              <option key={option.state_fips} value={option.state_fips}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span>County context</span>
          <select
            onChange={(event) => onSelectCounty(event.target.value || null)}
            value={overview.county_context.county_fips ?? ''}
          >
            {overview.county_context.options.length ? null : <option value="">No counties</option>}
            {overview.county_context.options.map((option) => (
              <option key={option.county_fips ?? option.label} value={option.county_fips ?? ''}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
      </div>
    </section>
  )
}

function PlacesValidationRows({
  rows,
}: {
  rows: CommunityPlacesValidationRowResponse[]
}): JSX.Element {
  if (!rows.length) {
    return <p className="muted">No model-vs-PLACES comparison rows are available.</p>
  }
  return (
    <div className="community-validation-table" role="table" aria-label="PLACES validation rows">
      <div role="row">
        <span role="columnheader">Condition</span>
        <span role="columnheader">Geography</span>
        <span role="columnheader">Model</span>
        <span role="columnheader">PLACES</span>
        <span role="columnheader">Delta</span>
      </div>
      {rows.map((row) => (
        <div role="row" key={`${row.condition_id}-${row.geography_level}-${row.state_fips ?? 'na'}-${row.county_fips ?? 'na'}`}>
          <span role="cell">{row.condition_id.replaceAll('_', ' ')}</span>
          <span role="cell">{row.geography_name ?? row.geography_level}</span>
          <span role="cell">{formatPercent(row.model_mean_predicted_probability)}</span>
          <span role="cell">{formatPercent(row.places_crude_prevalence_probability)}</span>
          <span role="cell">{formatSignedPercent(row.absolute_difference)}</span>
        </div>
      ))}
    </div>
  )
}

function CausalReportCard({
  report,
}: {
  report: CommunityCausalReportSummaryResponse
}): JSX.Element {
  return (
    <article className="metric-card" data-testid={`causal-report-${report.question_id}`}>
      <div>
        <p className="section-kicker">{report.status.replaceAll('_', ' ')}</p>
        <h4>{report.title}</h4>
      </div>
      <ul className="comparison-list compact-list">
        <li>
          <span>Treatment → outcome</span>
          <strong>
            {report.treatment ?? 'not reported'} → {report.outcome ?? 'not reported'}
          </strong>
        </li>
        <li>
          <span>Risk difference</span>
          <strong>{formatSignedPercent(report.risk_difference)}</strong>
        </li>
        <li>
          <span>Diagnostics</span>
          <strong>{report.diagnostic_status ?? 'not reported'}</strong>
        </li>
        <li>
          <span>Heterogeneity</span>
          <strong>{report.heterogeneity_status ?? 'not reported'}</strong>
        </li>
      </ul>
      <p className="muted">{report.caveat}</p>
      <p className="muted">Report: {report.report_path}</p>
    </article>
  )
}

export function CommunityContextPage({
  error,
  loading,
  onSelectCounty,
  onSelectState,
  onRetry,
  overview,
}: CommunityContextPageProps): JSX.Element {
  const validation = overview?.places_validation
  const causalReports = overview?.causal_reports ?? []

  return (
    <section className="page-stack community-page" data-testid="community-context-page">
      <section className="panel page-hero">
        <div className="panel-header">
          <p className="section-kicker">Community context</p>
          <h2>County, state, PLACES, and causal evidence</h2>
          <p>
            Inspect aggregate context and research evidence separately from the Explorer’s
            individual prediction score. This page is for provenance, validation, and comparison.
          </p>
        </div>
        <div className="page-stat-grid">
          <div className="page-stat">
            <span>State context</span>
            <strong>{overview?.state_context.available ? 'Ready' : '--'}</strong>
          </div>
          <div className="page-stat">
            <span>County context</span>
            <strong>{overview?.county_context.available ? 'Ready' : '--'}</strong>
          </div>
          <div className="page-stat">
            <span>PLACES rows</span>
            <strong>{validation ? validation.row_count : '--'}</strong>
          </div>
          <div className="page-stat">
            <span>Causal reports</span>
            <strong>{overview ? causalReports.length : '--'}</strong>
          </div>
        </div>
      </section>

      <section className="panel ethics-panel" data-testid="community-disclaimer">
        <div className="panel-header">
          <p className="section-kicker">Boundary</p>
          <h3>{disclaimers.causal.title}</h3>
          <p>{overview?.caveat ?? 'Community context does not directly change risk scores.'}</p>
          <p>{disclaimers.causal.body}</p>
        </div>
      </section>

      {error ? (
        <section className="panel">
          <div className="panel-inline-actions">
            <p className="error-banner">{error}</p>
            <button className="ghost-button" disabled={loading} onClick={onRetry} type="button">
              {loading ? 'Retrying...' : 'Retry community overview'}
            </button>
          </div>
        </section>
      ) : null}

      {!overview ? (
        <section className="panel">
          <p className="muted">
            {loading ? 'Loading community context...' : 'No community overview loaded yet.'}
          </p>
        </section>
      ) : (
        <>
          <GeographySelectors
            onSelectCounty={onSelectCounty}
            onSelectState={onSelectState}
            overview={overview}
          />

          <StateContextMap onSelectState={onSelectState} overview={overview} />

          <section className="page-card-grid" data-testid="community-context-cards">
            <ContextCard summary={overview.state_context} title="State ACS/SVI context" />
            <ContextCard summary={overview.county_context} title="County ACS/SVI context" />
            <ContextCard summary={overview.places_context} title="PLACES county context" />
          </section>

          <section className="panel" data-testid="places-validation-panel">
            <div className="panel-header">
              <h3>PLACES aggregate validation</h3>
              <p>
                Compare aggregate model risk patterns with CDC PLACES modeled estimates. PLACES is
                validation/context evidence, not a person-level label source.
              </p>
            </div>
            <div className="community-card-heading">
              <strong>{validation?.message ?? 'No validation report loaded'}</strong>
              <AvailabilityPill available={validation?.available ?? false} />
            </div>
            <PlacesValidationRows rows={validation?.rows ?? []} />
            <p className="muted">{validation?.caveat}</p>
          </section>

          <section className="panel" data-testid="causal-workbench-panel">
            <div className="panel-header">
              <h3>Causal workbench reports</h3>
              <p>
                These reports are local, assumption-bound analyses. They are shown as research
                evidence and are not used by the Explorer scoring endpoint.
              </p>
            </div>
            {causalReports.length ? (
              <div className="metric-card-grid">
                {causalReports.map((report) => (
                  <CausalReportCard key={report.question_id} report={report} />
                ))}
              </div>
            ) : (
              <p className="muted">No local causal workbench reports are available.</p>
            )}
          </section>
        </>
      )}
    </section>
  )
}
