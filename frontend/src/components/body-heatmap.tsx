import { useMemo, useState, type JSX, type KeyboardEvent } from 'react'
import { scaleThreshold } from 'd3-scale'

import bodySilhouette from '../assets/anatomy/servier-front-body-silhouette.png'
import type {
  HeatmapMode,
  OrganDefinition,
  OrganSummaryResponse,
  ScenarioCompareResponse,
} from '../types'

interface BodyHeatmapProps {
  comparison: ScenarioCompareResponse | null
  mode: HeatmapMode
  organs: OrganDefinition[]
  selectedOrganId: string | null
  onChangeMode: (mode: HeatmapMode) => void
  onSelectOrgan: (organId: string) => void
}

interface OrganShapeDefinition {
  anchorX: number
  anchorY: number
  calloutX: number
  calloutY: number
  shapes: Array<{
    d: string
    opacity?: number
  }>
}

interface ModeCopy {
  description: string
  emptyValue: string
  legendEnd: string
  legendStart: string
  legendTitle: string
  metricLabel: string
}

interface ModeCardData {
  description: string
  mode: HeatmapMode
  title: string
  value: string
}

interface OrganRenderData {
  fill: string
  isPreview: boolean
  isSelected: boolean
  label: string
  valueLabel: string
}

const organShapes: Record<string, OrganShapeDefinition> = {
  brain: {
    anchorX: 188,
    anchorY: 86,
    calloutX: 240,
    calloutY: 86,
    shapes: [
      {
        d: 'M140 67 C145 56 155 49 167 49 C180 49 191 56 196 69 C201 82 198 97 188 107 C178 117 162 120 149 112 C137 104 132 84 140 67 Z',
      },
      {
        d: 'M151 61 C156 66 159 74 158 82 M167 58 C173 64 176 73 174 83 M146 88 C151 91 155 98 155 105 M180 88 C175 92 171 99 171 106',
        opacity: 0.32,
      },
    ],
  },
  lungs: {
    anchorX: 205,
    anchorY: 196,
    calloutX: 246,
    calloutY: 176,
    shapes: [
      {
        d: 'M127 154 C114 162 106 178 106 197 C106 220 114 241 128 252 C139 260 151 255 156 242 C159 233 160 218 160 204 L160 170 C159 158 141 148 127 154 Z',
      },
      {
        d: 'M193 154 C206 162 214 178 214 197 C214 220 206 241 192 252 C181 260 169 255 164 242 C161 233 160 218 160 204 L160 170 C161 158 179 148 193 154 Z',
      },
      {
        d: 'M156 130 L156 162 M164 130 L164 162 M160 162 L149 178 M160 162 L171 178',
        opacity: 0.26,
      },
    ],
  },
  heart: {
    anchorX: 144,
    anchorY: 219,
    calloutX: 84,
    calloutY: 204,
    shapes: [
      {
        d: 'M153 197 C158 186 168 182 176 188 C183 194 184 204 179 212 L160 238 L140 212 C135 204 136 194 143 188 C150 182 159 186 153 197 Z',
      },
    ],
  },
  pancreas: {
    anchorX: 139,
    anchorY: 287,
    calloutX: 88,
    calloutY: 294,
    shapes: [
      {
        d: 'M123 276 C133 269 147 265 162 265 C181 265 197 270 205 278 C211 285 211 294 203 300 C195 307 180 312 163 312 C146 312 131 308 123 301 C116 295 115 283 123 276 Z',
      },
    ],
  },
  kidneys: {
    anchorX: 160,
    anchorY: 302,
    calloutX: 246,
    calloutY: 318,
    shapes: [
      {
        d: 'M127 284 C115 291 113 312 123 324 C133 337 150 329 151 311 C152 294 141 278 127 284 Z',
      },
      {
        d: 'M193 284 C205 291 207 312 197 324 C187 337 170 329 169 311 C168 294 179 278 193 284 Z',
      },
      {
        d: 'M151 309 C155 305 157 302 160 298 M169 309 C165 305 163 302 160 298',
        opacity: 0.28,
      },
    ],
  },
  joints: {
    anchorX: 160,
    anchorY: 405,
    calloutX: 78,
    calloutY: 392,
    shapes: [
      {
        d: 'M109 151 C116 151 121 156 121 163 C121 170 116 175 109 175 C102 175 97 170 97 163 C97 156 102 151 109 151 Z',
      },
      {
        d: 'M211 151 C218 151 223 156 223 163 C223 170 218 175 211 175 C204 175 199 170 199 163 C199 156 204 151 211 151 Z',
      },
      {
        d: 'M128 382 C136 382 142 389 142 397 C142 405 136 412 128 412 C120 412 114 405 114 397 C114 389 120 382 128 382 Z',
      },
      {
        d: 'M192 382 C200 382 206 389 206 397 C206 405 200 412 192 412 C184 412 178 405 178 397 C178 389 184 382 192 382 Z',
      },
    ],
  },
}

const deltaColor = scaleThreshold<number, string>()
  .domain([-0.05, -0.01, 0.01, 0.05])
  .range(['#0072b2', '#56b4e9', '#64748b', '#e69f00', '#d55e00'])

const riskColor = scaleThreshold<number, string>()
  .domain([0.15, 0.35])
  .range(['#0072b2', '#e69f00', '#d55e00'])

function formatDelta(delta: number): string {
  return `${delta >= 0 ? '+' : ''}${(delta * 100).toFixed(1)}%`
}

function formatPercent(value: number): string {
  return `${(value * 100).toFixed(1)}%`
}

function formatModeValue(
  mode: HeatmapMode,
  baseline: OrganSummaryResponse | undefined,
  candidate: OrganSummaryResponse | undefined,
  deltaScore: number | undefined,
): string {
  if (mode === 'baseline') {
    return baseline ? formatPercent(baseline.score) : '--'
  }
  if (mode === 'scenario') {
    return candidate ? formatPercent(candidate.score) : '--'
  }
  return deltaScore != null ? formatDelta(deltaScore) : '--'
}

function getModeCopy(mode: HeatmapMode): ModeCopy {
  if (mode === 'baseline') {
    return {
      description: 'Current organ risk based on the starting profile.',
      emptyValue: '--',
      legendEnd: 'Higher current risk',
      legendStart: 'Lower current risk',
      legendTitle: 'Absolute risk scale',
      metricLabel: 'Current risk',
    }
  }
  if (mode === 'scenario') {
    return {
      description: 'What-if organ risk after applying the edited profile.',
      emptyValue: '--',
      legendEnd: 'Higher what-if risk',
      legendStart: 'Lower what-if risk',
      legendTitle: 'Absolute risk scale',
      metricLabel: 'What-if risk',
    }
  }
  return {
    description: 'How the what-if profile changes each organ versus current. Blue means improved and orange means worsened relative to current, not low or high absolute risk.',
    emptyValue: '--',
    legendEnd: 'Worsens vs current',
    legendStart: 'Improves vs current',
    legendTitle: 'Relative change scale',
    metricLabel: 'Change vs current',
  }
}

function organScoreMap(organs: OrganSummaryResponse[] | undefined): Map<string, OrganSummaryResponse> {
  return new Map((organs ?? []).map((organ) => [organ.organ_id, organ]))
}

export function BodyHeatmap({
  comparison,
  mode,
  organs,
  selectedOrganId,
  onChangeMode,
  onSelectOrgan,
}: BodyHeatmapProps): JSX.Element {
  const [hoveredOrganId, setHoveredOrganId] = useState<string | null>(null)
  const supportedOrgans = organs.filter((organ) => organShapes[organ.organ_id] !== undefined)
  const byDelta = useMemo(
    () => new Map((comparison?.organ_deltas ?? []).map((item) => [item.organ_id, item])),
    [comparison],
  )
  const byBaseline = useMemo(
    () => organScoreMap(comparison?.baseline.organs),
    [comparison],
  )
  const byCandidate = useMemo(
    () => organScoreMap(comparison?.candidate.organs),
    [comparison],
  )
  const previewOrganId =
    hoveredOrganId ?? (selectedOrganId && organShapes[selectedOrganId] ? selectedOrganId : null)
  const copy = getModeCopy(mode)

  const previewLabel =
    supportedOrgans.find((organ) => organ.organ_id === previewOrganId)?.label ?? 'Choose an organ'

  const organRenderData = useMemo(() => {
    const rendered = new Map<string, OrganRenderData>()
    for (const organ of supportedOrgans) {
      const delta = byDelta.get(organ.organ_id)
      const baseline = byBaseline.get(organ.organ_id)
      const candidate = byCandidate.get(organ.organ_id)
      const isSelected = selectedOrganId === organ.organ_id
      const isPreview = previewOrganId === organ.organ_id

      let fill = '#4b5563'
      let valueLabel = copy.emptyValue

      if (mode === 'delta' && delta) {
        fill = deltaColor(delta.score_delta)
        valueLabel = formatDelta(delta.score_delta)
      } else if (mode === 'baseline' && baseline) {
        fill = riskColor(baseline.score)
        valueLabel = formatPercent(baseline.score)
      } else if (mode === 'scenario' && candidate) {
        fill = riskColor(candidate.score)
        valueLabel = formatPercent(candidate.score)
      }

      rendered.set(organ.organ_id, {
        fill,
        isPreview,
        isSelected,
        label: organ.label,
        valueLabel,
      })
    }
    return rendered
  }, [byBaseline, byCandidate, byDelta, copy.emptyValue, mode, previewOrganId, selectedOrganId, supportedOrgans])

  const previewValue =
    previewOrganId != null ? organRenderData.get(previewOrganId)?.valueLabel ?? copy.emptyValue : copy.emptyValue
  const previewBaseline = previewOrganId != null ? byBaseline.get(previewOrganId) : undefined
  const previewCandidate = previewOrganId != null ? byCandidate.get(previewOrganId) : undefined
  const previewDelta = previewOrganId != null ? byDelta.get(previewOrganId)?.score_delta : undefined
  const modeCards: ModeCardData[] = [
    {
      mode: 'baseline',
      title: 'Current',
      value: formatModeValue('baseline', previewBaseline, previewCandidate, previewDelta),
      description: 'Starting profile',
    },
    {
      mode: 'scenario',
      title: 'What-if',
      value: formatModeValue('scenario', previewBaseline, previewCandidate, previewDelta),
      description: 'Edited profile',
    },
    {
      mode: 'delta',
      title: 'Change vs current',
      value: formatModeValue('delta', previewBaseline, previewCandidate, previewDelta),
      description: 'Difference vs current',
    },
  ]

  function clearPreview(organId: string): void {
    setHoveredOrganId((current) => (current === organId ? null : current))
  }

  function handleKeyboardSelection(
    event: KeyboardEvent<SVGGElement>,
    organId: string,
  ): void {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault()
      onSelectOrgan(organId)
    }
  }

  return (
    <section className="panel heatmap-panel" data-testid="body-heatmap">
      <div className="panel-header heatmap-header">
        <div>
          <h2>Organ heatmap</h2>
          <p>Overview first, then inspect the selected organ in the drill-down.</p>
        </div>
      </div>

      <div className="heatmap-view-toggle" role="group" aria-label="Heatmap view mode">
        {modeCards.map((card) => (
          <button
            aria-pressed={mode === card.mode}
            className={mode === card.mode ? 'heatmap-mode-card active' : 'heatmap-mode-card'}
            data-testid={`heatmap-mode-${card.mode}`}
            key={card.mode}
            onClick={() => onChangeMode(card.mode)}
            type="button"
          >
            <span className="heatmap-mode-card-title">{card.title}</span>
            <strong className="heatmap-mode-card-value">{card.value}</strong>
            <span className="heatmap-mode-card-copy">{card.description}</span>
          </button>
        ))}
      </div>

      <div className="heatmap-status-bar">
        <div className="heatmap-preview-summary">
          <p className="section-kicker">Preview region</p>
          <strong className="heatmap-selected-label">{previewLabel}</strong>
        </div>
        <div className="heatmap-preview-summary metric">
          <p className="section-kicker">{copy.metricLabel}</p>
          <strong className="heatmap-selected-delta">{previewValue}</strong>
        </div>
      </div>

      <p className="heatmap-mode-copy">{copy.description}</p>

      <svg
        aria-label="Body impact explorer heatmap"
        className="body-map"
        viewBox="0 0 320 560"
      >
        <defs>
          <filter id="organGlow" height="180%" width="180%" x="-40%" y="-40%">
            <feGaussianBlur result="blur" stdDeviation="4" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>

        <image
          className="body-reference-image"
          href={bodySilhouette}
          height="452"
          preserveAspectRatio="xMidYMid meet"
          width="176"
          x="72"
          y="42"
        />

        {supportedOrgans.map((organ) => {
          const definition = organShapes[organ.organ_id]
          const renderData = organRenderData.get(organ.organ_id)
          const isSelected = renderData?.isSelected ?? false
          const isPreview = renderData?.isPreview ?? false

          return (
            <g
              aria-label={`${renderData?.label ?? organ.label} ${renderData?.valueLabel ?? ''}`}
              className={
                isSelected ? 'organ selected' : isPreview ? 'organ preview' : 'organ'
              }
              data-testid={`organ-${organ.organ_id}`}
              key={organ.organ_id}
              aria-pressed={isSelected}
              onBlur={() => clearPreview(organ.organ_id)}
              onClick={() => onSelectOrgan(organ.organ_id)}
              onFocus={() => setHoveredOrganId(organ.organ_id)}
              onKeyDown={(event) => handleKeyboardSelection(event, organ.organ_id)}
              onMouseEnter={() => setHoveredOrganId(organ.organ_id)}
              onMouseLeave={() => clearPreview(organ.organ_id)}
              role="button"
              tabIndex={0}
            >
              <title>
                {renderData?.label ?? organ.label}
                {renderData?.valueLabel ? ` ${renderData.valueLabel}` : ''}
              </title>
              {definition.shapes.map((shape) => (
                <path
                  d={shape.d}
                  fill={renderData?.fill ?? '#4b5563'}
                  filter={isPreview || isSelected ? 'url(#organGlow)' : undefined}
                  key={`${organ.organ_id}-${shape.d}`}
                  opacity={shape.opacity ?? 1}
                />
              ))}
            </g>
          )
        })}

        {supportedOrgans.map((organ) => {
          const definition = organShapes[organ.organ_id]
          const renderData = organRenderData.get(organ.organ_id)
          const isSelected = renderData?.isSelected ?? false
          const isPreview = renderData?.isPreview ?? false
          const calloutWidth = organ.label.length > 7 ? 86 : 74
          const calloutHeight = 28
          const boxX = definition.calloutX - calloutWidth / 2
          const boxY = definition.calloutY - calloutHeight / 2
          const lineEndX = definition.calloutX < 160 ? boxX + calloutWidth : boxX

          return (
            <g
              aria-label={`${renderData?.label ?? organ.label} callout`}
              aria-pressed={isSelected}
              className={
                isSelected
                  ? 'organ-callout selected'
                  : isPreview
                    ? 'organ-callout preview'
                    : 'organ-callout'
              }
              data-testid={`organ-callout-${organ.organ_id}`}
              key={`${organ.organ_id}-callout`}
              onBlur={() => clearPreview(organ.organ_id)}
              onClick={() => onSelectOrgan(organ.organ_id)}
              onFocus={() => setHoveredOrganId(organ.organ_id)}
              onKeyDown={(event) => handleKeyboardSelection(event, organ.organ_id)}
              onMouseEnter={() => setHoveredOrganId(organ.organ_id)}
              onMouseLeave={() => clearPreview(organ.organ_id)}
              role="button"
              tabIndex={0}
            >
              <path
                className="organ-callout-line"
                d={`M${definition.anchorX} ${definition.anchorY} L${(definition.anchorX + lineEndX) / 2} ${definition.anchorY} L${lineEndX} ${definition.calloutY}`}
              />
              <rect
                className="organ-callout-box"
                height={calloutHeight}
                rx="14"
                width={calloutWidth}
                x={boxX}
                y={boxY}
              />
              <text
                className="organ-callout-label"
                textAnchor="middle"
                x={definition.calloutX}
                y={definition.calloutY + 4}
              >
                {organ.label}
              </text>
            </g>
          )
        })}
      </svg>

      <div className="legend">
        <p className="legend-title">{copy.legendTitle}</p>
        <div className={mode === 'delta' ? 'legend-scale delta' : 'legend-scale risk'} />
        <div className="legend-labels">
          <span>{copy.legendStart}</span>
          <span>{copy.legendEnd}</span>
        </div>
        <ul className="legend-buckets" aria-label="Heatmap color meanings">
          {mode === 'delta' ? (
            <>
              <li><span className="legend-swatch delta-improves" /> Blue: improves</li>
              <li><span className="legend-swatch delta-neutral" /> Gray: little change</li>
              <li><span className="legend-swatch delta-worsens" /> Orange: worsens</li>
            </>
          ) : (
            <>
              <li><span className="legend-swatch risk-lower" /> Blue: lower band</li>
              <li><span className="legend-swatch risk-moderate" /> Amber: moderate band</li>
              <li><span className="legend-swatch risk-higher" /> Orange: higher band</li>
            </>
          )}
        </ul>
      </div>
    </section>
  )
}
