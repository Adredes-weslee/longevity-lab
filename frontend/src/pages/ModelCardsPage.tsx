import type { JSX } from 'react'

import type {
  MetadataBootstrapResponse,
  ScenarioCompareResponse,
} from '../types'

interface ModelCardsPageProps {
  bootstrap: MetadataBootstrapResponse
  comparison: ScenarioCompareResponse | null
}

function formatList(values: string[]): string {
  return values.length ? values.join(', ') : 'Not available in active bundle'
}

export function ModelCardsPage({
  bootstrap,
  comparison,
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
            Detailed benchmark metrics remain local generated artifacts until a model-card endpoint
            is added.
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
