import type { JSX } from 'react'

import { disclaimers } from '../content/disclaimers'
import type {
  ConditionModelCardResponse,
  MetadataBootstrapResponse,
  ModelCardBundleResponse,
  ModelMetricSetResponse,
  ScenarioCompareResponse,
} from '../types'

interface ModelCardsPageProps {
  bootstrap: MetadataBootstrapResponse
  comparison: ScenarioCompareResponse | null
  error: string | null
  loading: boolean
  modelCards: ModelCardBundleResponse | null
  onRetry: () => void
}

function formatList(values: string[]): string {
  return values.length ? values.join(', ') : 'Not available in active bundle'
}

function formatMetric(value: number | null, digits = 3): string {
  return value == null ? 'n/a' : value.toFixed(digits)
}

function formatPercent(value: number | null): string {
  return value == null ? 'n/a' : `${(value * 100).toFixed(1)}%`
}

function metricSummary(metrics: ModelMetricSetResponse): string {
  return `ROC-AUC ${formatMetric(metrics.roc_auc)} · AP ${formatMetric(metrics.average_precision)} · Brier ${formatMetric(metrics.brier_score)}`
}

function conditionCard(card: ConditionModelCardResponse): JSX.Element {
  return (
    <article className="metric-card" key={card.condition_id}>
      <div>
        <p className="section-kicker">{card.label}</p>
        <h4>{card.metrics_available ? metricSummary(card.calibrated_metrics) : 'Metrics unavailable'}</h4>
      </div>
      <ul className="comparison-list compact-list">
        <li>
          <span>Rows</span>
          <strong>{card.rows_total?.toLocaleString() ?? 'n/a'}</strong>
        </li>
        <li>
          <span>Positive rate</span>
          <strong>{formatPercent(card.positive_rate)}</strong>
        </li>
        <li>
          <span>AQI AP lift</span>
          <strong>{formatMetric(card.aqi_average_precision_delta, 4)}</strong>
        </li>
        <li>
          <span>Pollutant AP lift</span>
          <strong>{formatMetric(card.pollutant_average_precision_delta, 4)}</strong>
        </li>
        <li>
          <span>Features</span>
          <strong>{card.feature_count ?? card.features.length}</strong>
        </li>
        <li>
          <span>Context AP lift</span>
          <strong>{formatMetric(card.context_average_precision_delta, 4)}</strong>
        </li>
        <li>
          <span>Context features</span>
          <strong>
            {card.context_feature_count
              ? `${card.context_feature_count}: ${card.context_features.join(', ')}`
              : 'None declared'}
          </strong>
        </li>
        <li>
          <span>Uncertainty interval</span>
          <strong>
            {card.uncertainty_method
              ? `${formatPercent(card.uncertainty_half_width)} half-width`
              : 'Not declared'}
          </strong>
        </li>
        <li>
          <span>Calibration ECE</span>
          <strong>{formatMetric(card.uncertainty_expected_calibration_error, 4)}</strong>
        </li>
        <li>
          <span>Interval coverage</span>
          <strong>{formatPercent(card.uncertainty_empirical_coverage)}</strong>
        </li>
      </ul>
    </article>
  )
}

export function ModelCardsPage({
  bootstrap,
  comparison,
  error,
  loading,
  modelCards,
  onRetry,
}: ModelCardsPageProps): JSX.Element {
  const model = bootstrap.model_metadata
  const runtime = bootstrap.runtime
  const conditionCount = bootstrap.conditions.length
  const organCount = bootstrap.organs.length
  const metadataFromComparison = comparison?.model_metadata

  return (
    <section className="page-stack" data-testid="model-cards-page">
      <section className="panel page-hero">
        <div className="panel-header">
          <p className="section-kicker">Model cards</p>
          <h2>Active scoring contract</h2>
          <p>
            The UI only reports model metadata that the backend exposes through the v2 contract.
            Detailed benchmark metrics are loaded from trusted local artifact bundles when
            artifact-backed scoring is active.
          </p>
        </div>
        <div className="page-stat-grid">
          <div className="page-stat">
            <span>Runtime</span>
            <strong>{runtime.engine_mode}</strong>
          </div>
          <div className="page-stat">
            <span>Conditions</span>
            <strong>{conditionCount}</strong>
          </div>
          <div className="page-stat">
            <span>Organs</span>
            <strong>{organCount}</strong>
          </div>
        </div>
      </section>

      <section className="page-card-grid">
        <article className="panel info-card">
          <div className="panel-header">
            <h3>Runtime provenance</h3>
            <p>{runtime.message}</p>
          </div>
          <dl className="metadata-list">
            <div>
              <dt>Engine source</dt>
              <dd>{runtime.engine_source}</dd>
            </div>
            <div>
              <dt>Artifact ID</dt>
              <dd>{model.artifact_id ?? 'No artifact selected'}</dd>
            </div>
            <div>
              <dt>Data vintage</dt>
              <dd>{model.data_vintage ?? 'Not declared'}</dd>
            </div>
            <div>
              <dt>Dataset</dt>
              <dd>
                {model.dataset_name && model.dataset_version
                  ? `${model.dataset_name} ${model.dataset_version}`
                  : 'Not declared'}
              </dd>
            </div>
          </dl>
        </article>

        <article className="panel info-card">
          <div className="panel-header">
            <h3>Explanation and uncertainty</h3>
            <p>
              These fields describe what the active bundle can surface, not a guarantee that every
              condition row has an explanation or uncertainty interval.
            </p>
          </div>
          <dl className="metadata-list">
            <div>
              <dt>Explanation methods</dt>
              <dd>{formatList(model.explanation_methods)}</dd>
            </div>
            <div>
              <dt>Uncertainty</dt>
              <dd>
                {model.uncertainty_available
                  ? formatList(model.uncertainty_methods)
                  : 'Not available in active bundle'}
              </dd>
            </div>
            <div>
              <dt>Context geography</dt>
              <dd>
                {model.contextual_geography.available
                  ? `${model.contextual_geography.levels.join(', ')} (${model.contextual_geography.source ?? 'source not declared'})`
                  : 'No contextual geography declared'}
              </dd>
            </div>
          </dl>
        </article>

        <article className="panel info-card" data-testid="model-context-section">
          <div className="panel-header">
            <h3>Context and subgroup caveats</h3>
            <p>
              Context rows show state-year ACS/SVI signals only when manifest-declared. Subgroup
              metrics are audit evidence and should be interpreted with sample-size caveats.
            </p>
          </div>
          <dl className="metadata-list">
            <div>
              <dt>Context status</dt>
              <dd>
                {model.contextual_geography.available
                  ? 'Active state-year context'
                  : 'No active context features'}
              </dd>
            </div>
            <div>
              <dt>Context vintage</dt>
              <dd>
                {model.contextual_geography.data_vintage ?? 'No active context vintage declared'}
              </dd>
            </div>
            <div>
              <dt>Context feature list</dt>
              <dd>
                {model.contextual_geography.features.length
                  ? model.contextual_geography.features.join(', ')
                  : 'No active ACS/SVI context declared'}
              </dd>
            </div>
            <div>
              <dt>Subgroup caveat</dt>
              <dd>Slice metrics can be unstable for small or underrepresented groups.</dd>
            </div>
          </dl>
        </article>
      </section>

      <section className="panel ethics-panel" data-testid="model-disclaimer">
        <div className="panel-header">
          <p className="section-kicker">Interpretation limits</p>
          <h3>{disclaimers.prediction.title}</h3>
          <p>{disclaimers.prediction.body}</p>
          <p>{disclaimers.uncertainty.body}</p>
          <p>{disclaimers.causal.body}</p>
        </div>
      </section>

      <section className="panel" data-testid="model-card-metrics">
        <div className="panel-header">
          <h3>Model-card metrics</h3>
          <p>
            Condition-level metrics come from the active bundle's generated metrics JSON files,
            not from hard-coded frontend copy.
          </p>
        </div>
        {loading ? <p className="muted">Loading model-card metrics.</p> : null}
        {error ? (
          <div className="panel-inline-actions">
            <p className="error-banner">{error}</p>
            <button className="ghost-button" onClick={onRetry} type="button">
              Retry model cards
            </button>
          </div>
        ) : null}
        {!loading && !error && modelCards ? (
          modelCards.available ? (
            <>
              <p className="muted">{modelCards.message}</p>
              <div className="metric-card-grid">
                {modelCards.condition_cards.map(conditionCard)}
              </div>
            </>
          ) : (
            <p className="muted">{modelCards.message}</p>
          )
        ) : null}
      </section>

      <section className="panel">
        <div className="panel-header">
          <h3>Contract consistency</h3>
          <p>
            Bootstrap and scenario compare responses should describe the same active model when
            the same backend process serves both requests.
          </p>
        </div>
        {metadataFromComparison ? (
          <ul className="comparison-list">
            <li>
              <span>Bootstrap model mode</span>
              <strong>{model.model_mode}</strong>
            </li>
            <li>
              <span>Scenario model mode</span>
              <strong>{metadataFromComparison.model_mode}</strong>
            </li>
            <li>
              <span>Scenario artifact</span>
              <strong>{metadataFromComparison.artifact_id ?? 'No artifact selected'}</strong>
            </li>
          </ul>
        ) : (
          <p className="muted">Scenario comparison has not loaded yet.</p>
        )}
      </section>
    </section>
  )
}
