import type { JSX } from 'react'

import type { PipelineStatusResponse } from '../types'

interface PipelineStatusPanelProps {
  status: PipelineStatusResponse | null
  error: string | null
  loading?: boolean
  onRetry?: () => void
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

export function PipelineStatusPanel({
  status,
  error,
  loading = false,
  onRetry,
}: PipelineStatusPanelProps): JSX.Element {
  return (
    <section className="panel" data-testid="pipeline-status">
      <div className="panel-header">
        <h2>Data integration status</h2>
        <p>Quick check that raw + processed pipeline outputs exist locally.</p>
      </div>

      {error ? (
        <div className="panel-inline-actions">
          <p className="muted">{error}</p>
          {onRetry ? (
            <button className="ghost-button" disabled={loading} onClick={onRetry} type="button">
              {loading ? 'Retrying...' : 'Retry'}
            </button>
          ) : null}
        </div>
      ) : null}

      {!status ? (
        <p className="muted">
          {loading ? 'Loading pipeline status...' : 'No pipeline status loaded yet.'}
        </p>
      ) : (
        <>
          <ul className="pipeline-status-list">
            {status.artifacts.map((artifact) => (
              <li key={artifact.artifact_id}>
                <span>{artifact.label}</span>
                <span
                  className={
                    artifact.exists ? 'status-pill status-pill-ok' : 'status-pill status-pill-missing'
                  }
                >
                  {artifact.exists ? 'Ready' : 'Missing'}
                </span>
                <span className="muted">
                  {artifact.exists
                    ? [formatBytes(artifact.bytes), artifact.path].filter(Boolean).join(' ')
                    : artifact.path}
                </span>
              </li>
            ))}
          </ul>

          {status.provenance.length ? (
            <details className="pipeline-provenance">
              <summary>Provenance summaries</summary>
              <ul className="pipeline-provenance-list">
                {status.provenance.map((item) => (
                  <li key={item.path}>
                    <strong>
                      {item.dataset_name} ({item.dataset_version})
                    </strong>
                    <div className="muted">{item.retrieved_at}</div>
                    {Object.keys(item.extra).length ? (
                      <pre className="provenance-extra">
                        {JSON.stringify(item.extra, null, 2)}
                      </pre>
                    ) : null}
                  </li>
                ))}
              </ul>
            </details>
          ) : null}
        </>
      )}
    </section>
  )
}
