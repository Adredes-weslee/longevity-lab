import type { JSX } from 'react'

import { PipelineStatusPanel } from '../components/pipeline-status'
import type {
  MetadataBootstrapResponse,
  PipelineStatusResponse,
} from '../types'

interface DataEvidencePageProps {
  bootstrap: MetadataBootstrapResponse
  status: PipelineStatusResponse | null
  error: string | null
  loading: boolean
  onRetry: () => void
}

export function DataEvidencePage({
  bootstrap,
  status,
  error,
  loading,
  onRetry,
}: DataEvidencePageProps): JSX.Element {
  const readyCount = status?.artifacts.filter((artifact) => artifact.exists).length ?? 0
  const totalCount = status?.artifacts.length ?? 0
  const provenanceCount = status?.provenance.length ?? 0

  return (
    <section className="page-stack data-page" data-testid="data-evidence-page">
      <section className="panel page-hero">
        <div className="panel-header">
          <p className="section-kicker">Data evidence</p>
          <h2>Pipeline assets and provenance</h2>
          <p>
            This page separates local data readiness from the risk explorer. It reads the live
            pipeline status endpoint rather than assuming raw or processed assets exist.
          </p>
        </div>
        <div className="page-stat-grid">
          <div className="page-stat">
            <span>API contract</span>
            <strong>{bootstrap.contract_version}</strong>
          </div>
          <div className="page-stat">
            <span>Artifacts ready</span>
            <strong>{totalCount ? `${readyCount}/${totalCount}` : '--'}</strong>
          </div>
          <div className="page-stat">
            <span>Provenance files</span>
            <strong>{status ? provenanceCount : '--'}</strong>
          </div>
        </div>
      </section>

      <PipelineStatusPanel
        error={error}
        loading={loading}
        onRetry={onRetry}
        status={status}
      />
    </section>
  )
}
