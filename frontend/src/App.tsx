import { useCallback, useEffect, useRef, useState, type JSX } from 'react'

import {
  compareScenarios,
  fetchBootstrap,
  fetchContextGeographies,
  fetchEvidenceStatus,
  fetchModelCards,
} from './api/client'
import { DataEvidencePage } from './pages/DataEvidencePage'
import { ExplorerPage } from './pages/ExplorerPage'
import { ModelCardsPage } from './pages/ModelCardsPage'
import { ScenarioLabPage } from './pages/ScenarioLabPage'
import { useScenario } from './state/scenario-context'
import type {
  HeatmapMode,
  MetadataBootstrapResponse,
  ModelCardBundleResponse,
  EvidenceStatusResponse,
  GeographyOptionsResponse,
  ScenarioCompareResponse,
} from './types'

type AppView = 'explorer' | 'data' | 'models' | 'lab'

const navItems: Array<{ label: string; view: AppView }> = [
  { label: 'Explorer', view: 'explorer' },
  { label: 'Data evidence', view: 'data' },
  { label: 'Model cards', view: 'models' },
  { label: 'Scenario lab', view: 'lab' },
]

function getViewFromHash(hash: string): AppView {
  if (hash === '#/data') {
    return 'data'
  }
  if (hash === '#/models') {
    return 'models'
  }
  if (hash === '#/lab') {
    return 'lab'
  }
  return 'explorer'
}

function hashForView(view: AppView): string {
  return view === 'explorer' ? '/explorer' : `/${view}`
}

function App(): JSX.Element {
  const { state, dispatch } = useScenario()
  const [bootstrap, setBootstrap] = useState<MetadataBootstrapResponse | null>(null)
  const [bootstrapLoading, setBootstrapLoading] = useState(false)
  const [geographies, setGeographies] = useState<GeographyOptionsResponse | null>(null)
  const [geographiesLoading, setGeographiesLoading] = useState(false)
  const [geographiesError, setGeographiesError] = useState<string | null>(null)
  const [comparison, setComparison] = useState<ScenarioCompareResponse | null>(null)
  const [evidenceStatus, setEvidenceStatus] = useState<EvidenceStatusResponse | null>(null)
  const [evidenceError, setEvidenceError] = useState<string | null>(null)
  const [evidenceLoading, setEvidenceLoading] = useState(false)
  const [modelCards, setModelCards] = useState<ModelCardBundleResponse | null>(null)
  const [modelCardsError, setModelCardsError] = useState<string | null>(null)
  const [modelCardsLoading, setModelCardsLoading] = useState(false)
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

  const runComparison = useCallback(async (): Promise<void> => {
    const nextSequence = requestSequence.current + 1
    requestSequence.current = nextSequence
    setBusy(true)
    setErrorMessage(null)
    try {
      const nextComparison = await compareScenarios({
        baseline: state.baseline,
        candidate: state.candidate,
        geography: state.geography,
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
  }, [dispatch, state.baseline, state.candidate, state.geography, state.selectedOrganId])

  const loadGeographies = useCallback(async (year: number): Promise<void> => {
    setGeographiesLoading(true)
    setGeographiesError(null)
    try {
      const nextGeographies = await fetchContextGeographies(year)
      setGeographies(nextGeographies)
    } catch (error) {
      setGeographiesError(
        error instanceof Error ? error.message : 'Geography context unavailable.',
      )
    } finally {
      setGeographiesLoading(false)
    }
  }, [])

  const loadEvidenceStatus = useCallback(async (): Promise<void> => {
    setEvidenceLoading(true)
    setEvidenceError(null)
    try {
      const status = await fetchEvidenceStatus(2023)
      setEvidenceStatus(status)
    } catch (error) {
      setEvidenceError(
        error instanceof Error ? error.message : 'Evidence status unavailable.',
      )
    } finally {
      setEvidenceLoading(false)
    }
  }, [])

  const loadModelCards = useCallback(async (): Promise<void> => {
    setModelCardsLoading(true)
    setModelCardsError(null)
    try {
      const cards = await fetchModelCards()
      setModelCards(cards)
    } catch (error) {
      setModelCardsError(
        error instanceof Error ? error.message : 'Model-card metrics unavailable.',
      )
    } finally {
      setModelCardsLoading(false)
    }
  }, [])

  useEffect(() => {
    void loadBootstrap()
  }, [loadBootstrap])

  useEffect(() => {
    if (!bootstrap) {
      return
    }
    void loadGeographies(bootstrap.geography.default_year)
  }, [bootstrap, loadGeographies])

  useEffect(() => {
    if (state.geography || !geographies?.options.length) {
      return
    }
    const firstOption = geographies.options[0]
    dispatch({
      type: 'setGeography',
      geography: {
        level: firstOption.level,
        state_fips: firstOption.state_fips,
        year: firstOption.year,
      },
    })
  }, [dispatch, geographies, state.geography])

  useEffect(() => {
    function handleHashChange(): void {
      setView(getViewFromHash(window.location.hash))
    }

    window.addEventListener('hashchange', handleHashChange)
    return () => window.removeEventListener('hashchange', handleHashChange)
  }, [])

  useEffect(() => {
    if (view === 'data') {
      void loadEvidenceStatus()
    }
  }, [loadEvidenceStatus, view])

  useEffect(() => {
    if (view === 'models') {
      void loadModelCards()
    }
  }, [loadModelCards, view])

  useEffect(() => {
    if (!bootstrap) {
      return
    }
    const timeoutId = window.setTimeout(() => {
      void runComparison()
    }, 140)
    return () => window.clearTimeout(timeoutId)
  }, [bootstrap, runComparison])

  function navigate(nextView: AppView): void {
    window.location.hash = hashForView(nextView)
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">Lifestyle risk communication platform</p>
          <h1>Longevity Lab</h1>
          <p className="hero-copy">
            Explore how lifestyle and environment shift organ-level risk, inspect model
            provenance, and verify the data evidence behind the local workflow.
          </p>
        </div>
        <nav className="topbar-nav" aria-label="Primary">
          {navItems.map((item) => (
            <button
              className={view === item.view ? 'nav-pill active' : 'nav-pill'}
              key={item.view}
              onClick={() => navigate(item.view)}
              type="button"
            >
              {item.label}
            </button>
          ))}
        </nav>
      </header>

      {errorMessage ? <p className="error-banner">{errorMessage}</p> : null}

      {bootstrap ? (
        <>
          {view === 'explorer' ? (
            <ExplorerPage
              bootstrap={bootstrap}
              busy={busy}
              comparison={comparison}
              geographies={geographies}
              geographiesError={geographiesError}
              geographiesLoading={geographiesLoading}
              heatmapMode={heatmapMode}
              onChangeHeatmapMode={setHeatmapMode}
            />
          ) : null}
          {view === 'data' ? (
            <DataEvidencePage
              bootstrap={bootstrap}
              error={evidenceError}
              loading={evidenceLoading}
              onRetry={() => void loadEvidenceStatus()}
              status={evidenceStatus}
            />
          ) : null}
          {view === 'models' ? (
            <ModelCardsPage
              bootstrap={bootstrap}
              comparison={comparison}
              error={modelCardsError}
              loading={modelCardsLoading}
              modelCards={modelCards}
              onRetry={() => void loadModelCards()}
            />
          ) : null}
          {view === 'lab' ? (
            <ScenarioLabPage comparison={comparison} loading={busy} />
          ) : null}
        </>
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
