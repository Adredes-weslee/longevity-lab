import { useCallback, useEffect, useMemo, useRef, useState, type JSX } from 'react'

import { compareScenarios, fetchBootstrap, fetchPipelineStatus } from './api/client'
import { BodyHeatmap } from './components/body-heatmap'
import { ConditionInspector } from './components/condition-inspector'
import { PipelineStatusPanel } from './components/pipeline-status'
import { ScenarioForm } from './components/scenario-form'
import { useScenario } from './state/scenario-context'
import type {
  FeatureProfile,
  HeatmapMode,
  MetadataBootstrapResponse,
  PipelineStatusResponse,
  ScenarioCompareResponse,
} from './types'

type AppView = 'explorer' | 'data'

function getViewFromHash(hash: string): AppView {
  return hash === '#/data' ? 'data' : 'explorer'
}

function changedFeatureCount(
  baseline: FeatureProfile,
  candidate: FeatureProfile,
): number {
  let count = 0
  for (const field of Object.keys(baseline) as Array<keyof typeof baseline>) {
    if (baseline[field] !== candidate[field]) {
      count += 1
    }
  }
  return count
}

function App(): JSX.Element {
  const { state, dispatch } = useScenario()
  const [bootstrap, setBootstrap] = useState<MetadataBootstrapResponse | null>(null)
  const [bootstrapLoading, setBootstrapLoading] = useState(false)
  const [comparison, setComparison] = useState<ScenarioCompareResponse | null>(null)
  const [pipelineStatus, setPipelineStatus] = useState<PipelineStatusResponse | null>(null)
  const [pipelineError, setPipelineError] = useState<string | null>(null)
  const [pipelineLoading, setPipelineLoading] = useState(false)
  const [busy, setBusy] = useState(false)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const [heatmapMode, setHeatmapMode] = useState<HeatmapMode>('delta')
  const [view, setView] = useState<AppView>(() => getViewFromHash(window.location.hash))
  const requestSequence = useRef(0)

  const loadBootstrap = useCallback(async (): Promise<void> => {
    setBootstrapLoading(true)
    setErrorMessage(null)
    try {
      const metadata = await fetchBootstrap()
      setBootstrap(metadata)
    } catch (error) {
      setErrorMessage(
        error instanceof Error ? error.message : 'Metadata bootstrap failed.',
      )
    } finally {
      setBootstrapLoading(false)
    }
  }, [])

  const runComparison = useCallback(async (
    baseline: FeatureProfile,
    candidate: FeatureProfile,
  ): Promise<void> => {
    const nextSequence = requestSequence.current + 1
    requestSequence.current = nextSequence
    setBusy(true)
    setErrorMessage(null)
    try {
      const nextComparison = await compareScenarios({
        baseline,
        candidate,
      })
      if (requestSequence.current !== nextSequence) {
        return
      }
      setComparison(nextComparison)
      if (!state.selectedOrganId && nextComparison.organ_deltas.length > 0) {
        dispatch({
          type: 'selectOrgan',
          organId: nextComparison.organ_deltas[0].organ_id,
        })
      }
    } catch (error) {
      if (requestSequence.current !== nextSequence) {
        return
      }
      setErrorMessage(
        error instanceof Error ? error.message : 'Scenario comparison failed.',
      )
    } finally {
      if (requestSequence.current === nextSequence) {
        setBusy(false)
      }
    }
  }, [dispatch, state.selectedOrganId])

  useEffect(() => {
    void loadBootstrap()
  }, [loadBootstrap])

  useEffect(() => {
    function handleHashChange(): void {
      setView(getViewFromHash(window.location.hash))
    }

    window.addEventListener('hashchange', handleHashChange)
    return () => window.removeEventListener('hashchange', handleHashChange)
  }, [])

  const loadPipelineStatus = useCallback(async (): Promise<void> => {
    setPipelineLoading(true)
    setPipelineError(null)
    try {
      const status = await fetchPipelineStatus(2023)
      setPipelineStatus(status)
    } catch (error) {
      setPipelineError(
        error instanceof Error ? error.message : 'Pipeline status unavailable.',
      )
    } finally {
      setPipelineLoading(false)
    }
  }, [])

  useEffect(() => {
    if (view === 'data') {
      void loadPipelineStatus()
    }
  }, [loadPipelineStatus, view])

  useEffect(() => {
    if (!bootstrap) {
      return
    }
    const timeoutId = window.setTimeout(() => {
      void runComparison(state.baseline, state.candidate)
    }, 140)
    return () => window.clearTimeout(timeoutId)
  }, [bootstrap, runComparison, state.baseline, state.candidate])

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

  function navigate(nextView: AppView): void {
    window.location.hash = nextView === 'data' ? '/data' : '/explorer'
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">Lifestyle risk communication explorer</p>
          <h1>Longevity Lab</h1>
          <p className="hero-copy">
            Explore how lifestyle and environment shift organ-level risk, then inspect the
            drivers behind each change.
          </p>
        </div>
        <nav className="topbar-nav" aria-label="Primary">
          <button
            className={view === 'explorer' ? 'nav-pill active' : 'nav-pill'}
            onClick={() => navigate('explorer')}
            type="button"
          >
            Explorer
          </button>
          <button
            className={view === 'data' ? 'nav-pill active' : 'nav-pill'}
            onClick={() => navigate('data')}
            type="button"
          >
            Data integration
          </button>
        </nav>
      </header>

      {errorMessage ? <p className="error-banner">{errorMessage}</p> : null}

      {bootstrap ? (
        view === 'explorer' ? (
          <>
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
                    <h2>Educational use only</h2>
                    <p>
                      Compare lifestyle scenarios here, but do not treat these scores as medical
                      advice or diagnosis.
                    </p>
                  </div>
                </section>

                <ScenarioForm
                  busy={busy}
                  features={bootstrap.features}
                />
              </div>

              <div className="explorer-main">
                <BodyHeatmap
                  comparison={comparison}
                  mode={heatmapMode}
                  onChangeMode={setHeatmapMode}
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
        ) : (
          <section className="data-page">
            <section className="panel data-page-intro">
              <div className="panel-header">
                <h2>Data integration</h2>
                <p>
                  Keep pipeline health separate from the explorer so users can focus on the body
                  view, then switch here when you need to verify raw and processed assets.
                </p>
              </div>
            </section>
            <PipelineStatusPanel
              error={pipelineError}
              loading={pipelineLoading}
              onRetry={() => void loadPipelineStatus()}
              status={pipelineStatus}
            />
          </section>
        )
      ) : (
        <section className="panel">
          <div className="panel-header">
            <h2>Bootstrapping</h2>
            <p>{bootstrapLoading ? 'Loading API metadata.' : 'Waiting for API metadata.'}</p>
          </div>
          <div className="panel-inline-actions">
            <p className="muted">Start the backend API, then retry loading the metadata bundle.</p>
            <button
              className="ghost-button"
              disabled={bootstrapLoading}
              onClick={() => void loadBootstrap()}
              type="button"
            >
              {bootstrapLoading ? 'Loading...' : 'Retry bootstrap'}
            </button>
          </div>
        </section>
      )}
    </div>
  )
}

export default App
