import type { JSX } from 'react'

import { disclaimers } from '../content/disclaimers'
import type {
  EvidenceAssetGroup,
  EvidenceAssetStatus,
  EvidenceInactiveGap,
  EvidenceReportSummary,
  EvidenceSourceSummary,
  EvidenceStatusResponse,
  MetadataBootstrapResponse,
} from '../types'

interface DataEvidencePageProps {
  bootstrap: MetadataBootstrapResponse
  status: EvidenceStatusResponse | null
  error: string | null
  loading: boolean
  onRetry: () => void
}

function formatBytes(bytes: number | null): string {
  if (bytes == null) {
    return ''
  }
  const units = ['B', 'KB', 'MB', 'GB']
  let value = bytes
  let unitIndex = 0
  while (value >= 1024 && unitIndex < units.length - 1) {
    value /= 1024
    unitIndex += 1
  }
  return `${value.toFixed(unitIndex === 0 ? 0 : 1)} ${units[unitIndex]}`
}

function StatusPill({ ready }: { ready: boolean }): JSX.Element {
  return (
    <span className={ready ? 'status-pill status-pill-ok' : 'status-pill status-pill-missing'}>
      {ready ? 'Ready' : 'Missing'}
    </span>
  )
}

function SourceCard({ source }: { source: EvidenceSourceSummary }): JSX.Element {
  return (
    <article className="metric-card">
      <div>
        <p className="section-kicker">{source.role.replaceAll('_', ' ')}</p>
        <h4>{source.title}</h4>
      </div>
      <ul className="comparison-list compact-list">
        <li>
          <span>Active in scoring</span>
          <strong>{source.active_in_model ? 'Yes' : 'No'}</strong>
        </li>
        <li>
          <span>Geography</span>
          <strong>{source.geography}</strong>
        </li>
        <li>
          <span>Landing path</span>
          <strong>{source.local_landing_path}</strong>
        </li>
      </ul>
      {source.caveat ? <p className="muted">{source.caveat}</p> : null}
    </article>
  )
}

function AssetRow({ asset }: { asset: EvidenceAssetStatus }): JSX.Element {
  return (
    <li>
      <span>{asset.label}</span>
      <StatusPill ready={asset.exists} />
      <span className="muted">
        {asset.exists
          ? [formatBytes(asset.bytes), asset.path].filter(Boolean).join(' ')
          : asset.path}
      </span>
      {asset.caveat ? <span className="muted">{asset.caveat}</span> : null}
    </li>
  )
}

function AssetGroupCard({ group }: { group: EvidenceAssetGroup }): JSX.Element {
  return (
    <section className="panel" data-testid={`asset-group-${group.group_id}`}>
      <div className="panel-header">
        <h3>{group.label}</h3>
        <p>
          {group.ready_count}/{group.total_count} expected evidence assets are present in this
          runtime.
        </p>
      </div>
      <ul className="pipeline-status-list">
        {group.assets.map((asset) => (
          <AssetRow asset={asset} key={asset.asset_id} />
        ))}
      </ul>
    </section>
  )
}

function ReportRow({ report }: { report: EvidenceReportSummary }): JSX.Element {
  return (
    <li>
      <span>{report.label}</span>
      <StatusPill ready={report.exists} />
      <span className="muted">
        {report.exists
          ? [formatBytes(report.bytes), report.path].filter(Boolean).join(' ')
          : report.path}
      </span>
      {report.caveat ? <span className="muted">{report.caveat}</span> : null}
    </li>
  )
}

function GapCard({ gap }: { gap: EvidenceInactiveGap }): JSX.Element {
  return (
    <article className="metric-card">
      <div>
        <p className="section-kicker">{gap.status.replaceAll('_', ' ')}</p>
        <h4>{gap.label}</h4>
      </div>
      <p className="muted">{gap.explanation}</p>
      <p className="muted">
        Evidence: {gap.evidence.length ? gap.evidence.join(', ') : 'No evidence listed'}
      </p>
      {gap.next_action ? <p className="muted">Next: {gap.next_action}</p> : null}
    </article>
  )
}

function ContextEvidenceSections({ status }: { status: EvidenceStatusResponse }): JSX.Element {
  const context = status.model_metadata.contextual_geography
  const countyGap = status.inactive_gaps.find((gap) => gap.gap_id === 'county_context_not_active')
  const placesGap = status.inactive_gaps.find((gap) => gap.gap_id === 'places_validation_only')

  return (
    <section className="page-card-grid context-evidence-grid" data-testid="context-evidence-sections">
      <article className="panel info-card" data-testid="active-state-context">
        <div className="panel-header">
          <h3>Active state-year context</h3>
          <p>
            ACS/SVI context affects scoring only when the active artifact manifest declares a
            state-year lookup contract.
          </p>
        </div>
        <dl className="metadata-list">
          <div>
            <dt>Status</dt>
            <dd>{context.available ? 'Active in artifact scoring' : 'Inactive for current runtime'}</dd>
          </div>
          <div>
            <dt>Source</dt>
            <dd>{context.source ?? 'Not declared by active model'}</dd>
          </div>
          <div>
            <dt>Context vintage</dt>
            <dd>{context.data_vintage ?? 'Not declared by active model'}</dd>
          </div>
          <div>
            <dt>Features</dt>
            <dd>{context.feature_count ? context.features.join(', ') : 'No active context features'}</dd>
          </div>
        </dl>
        <p className="muted">{context.caveat ?? 'State context is background context, not a personal scenario input.'}</p>
      </article>

      <article className="panel info-card" data-testid="inactive-county-context">
        <div className="panel-header">
          <h3>Inactive county context</h3>
          <p>
            County-level context remains separated because current BRFSS serving rows only support
            state-year semantics.
          </p>
        </div>
        <p className="muted">{countyGap?.explanation ?? 'County context is not served for predictions.'}</p>
        {countyGap?.evidence.length ? (
          <p className="muted">Evidence: {countyGap.evidence.join(', ')}</p>
        ) : null}
      </article>

      <article className="panel info-card" data-testid="validation-only-places">
        <div className="panel-header">
          <h3>Validation-only PLACES</h3>
          <p>
            PLACES is used for aggregate reasonableness checks and contextual evidence, not as
            person-level training labels.
          </p>
        </div>
        <p className="muted">{placesGap?.explanation ?? 'PLACES remains validation/context only.'}</p>
        {placesGap?.evidence.length ? (
          <p className="muted">Evidence: {placesGap.evidence.join(', ')}</p>
        ) : null}
      </article>
    </section>
  )
}

export function DataEvidencePage({
  bootstrap,
  status,
  error,
  loading,
  onRetry,
}: DataEvidencePageProps): JSX.Element {
  const readyCount =
    status?.asset_groups.reduce((total, group) => total + group.ready_count, 0) ?? 0
  const totalCount =
    status?.asset_groups.reduce((total, group) => total + group.total_count, 0) ?? 0
  const activeSourceCount = status?.sources.filter((source) => source.active_in_model).length ?? 0
  const activeFeatureCount = status?.feature_inventory.active_model_features.length ?? 0
  const conditionCount = bootstrap.conditions.length
  const organCount = bootstrap.organs.length

  return (
    <section className="page-stack data-page" data-testid="data-evidence-page">
      <section className="panel page-hero">
        <div className="panel-header">
          <p className="section-kicker">Data evidence</p>
          <h2>Active evidence, model scope, and known gaps</h2>
          <p>
            This page distinguishes what is actively used by the scoring artifact from local
            pipeline assets, validation-only reports, and geography context that is not yet served
            as a scenario input.
          </p>
          <p>
            Use the Community Context page to inspect county/state ACS/SVI, PLACES validation, and
            causal workbench reports as separate evidence surfaces.
          </p>
        </div>
        <div className="page-stat-grid">
          <div className="page-stat">
            <span>API contract</span>
            <strong>{bootstrap.contract_version}</strong>
          </div>
          <div className="page-stat">
            <span>Runtime assets</span>
            <strong>{totalCount ? `${readyCount}/${totalCount}` : '--'}</strong>
          </div>
          <div className="page-stat">
            <span>Active sources</span>
            <strong>{status ? activeSourceCount : '--'}</strong>
          </div>
          <div className="page-stat">
            <span>Active features</span>
            <strong>{status ? activeFeatureCount : '--'}</strong>
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

      <section className="panel ethics-panel" data-testid="data-disclaimer">
        <div className="panel-header">
          <p className="section-kicker">Use limits</p>
          <h3>{disclaimers.dataLimitations.title}</h3>
          <p>{disclaimers.dataLimitations.body}</p>
          <p>{disclaimers.intendedUse.body}</p>
        </div>
      </section>

      {error ? (
        <section className="panel">
          <div className="panel-inline-actions">
            <p className="error-banner">{error}</p>
            <button className="ghost-button" disabled={loading} onClick={onRetry} type="button">
              {loading ? 'Retrying...' : 'Retry evidence status'}
            </button>
          </div>
        </section>
      ) : null}

      {!status ? (
        <section className="panel">
          <p className="muted">
            {loading ? 'Loading evidence status...' : 'No evidence status loaded yet.'}
          </p>
        </section>
      ) : (
        <>
          <section className="page-card-grid">
            <article className="panel info-card">
              <div className="panel-header">
                <h3>Production artifact</h3>
                <p>{status.runtime.message}</p>
              </div>
              <dl className="metadata-list">
                <div>
                  <dt>Active bundle</dt>
                  <dd>{status.production_artifact.active_bundle_id ?? 'No artifact selected'}</dd>
                </div>
                <div>
                  <dt>Release download configured</dt>
                  <dd>
                    {status.production_artifact.release_download_configured ? 'Yes' : 'No'}
                  </dd>
                </div>
                <div>
                  <dt>Local bundle exists</dt>
                  <dd>{status.production_artifact.local_bundle_exists ? 'Yes' : 'No'}</dd>
                </div>
              </dl>
            </article>

            <article className="panel info-card">
              <div className="panel-header">
                <h3>Feature inventory</h3>
                <p>Scenario-editable features should be a subset of active model features.</p>
              </div>
              <dl className="metadata-list">
                <div>
                  <dt>Scenario inputs</dt>
                  <dd>{status.feature_inventory.scenario_editable.join(', ')}</dd>
                </div>
                <div>
                  <dt>Active model features</dt>
                  <dd>{status.feature_inventory.active_model_features.join(', ')}</dd>
                </div>
                <div>
                  <dt>Available context only</dt>
                  <dd>
                    {status.feature_inventory.available_pipeline_context_features.join(', ') ||
                      'No context features detected'}
                  </dd>
                </div>
              </dl>
            </article>
          </section>

          <section className="panel" data-testid="source-registry">
            <div className="panel-header">
              <h3>Public source registry</h3>
              <p>
                Active model sources train or score the artifact. Context and validation sources
                are visible evidence but are not silently folded into predictions.
              </p>
            </div>
            <div className="metric-card-grid">
              {status.sources.map((source) => (
                <SourceCard key={source.source_id} source={source} />
              ))}
            </div>
          </section>

          <ContextEvidenceSections status={status} />

          {status.asset_groups.map((group) => (
            <AssetGroupCard group={group} key={group.group_id} />
          ))}

          <section className="panel" data-testid="evidence-reports">
            <div className="panel-header">
              <h3>Generated reports</h3>
              <p>Reports are local audit evidence; predictive scores come from model artifacts.</p>
            </div>
            <ul className="pipeline-status-list">
              {status.reports.map((report) => (
                <ReportRow key={report.report_id} report={report} />
              ))}
            </ul>
          </section>

          <section className="panel" data-testid="inactive-gaps">
            <div className="panel-header">
              <h3>Known inactive gaps</h3>
              <p>
                These are implemented or available pieces that are intentionally not active in
                scoring until their serving semantics are defensible.
              </p>
            </div>
            <div className="metric-card-grid">
              {status.inactive_gaps.map((gap) => (
                <GapCard gap={gap} key={gap.gap_id} />
              ))}
            </div>
          </section>
        </>
      )}
    </section>
  )
}
