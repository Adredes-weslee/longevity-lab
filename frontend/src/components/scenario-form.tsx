import { useState, type ChangeEvent, type JSX } from 'react'

import { useScenario } from '../state/scenario-context'
import type {
  FeatureDefinition,
  FeatureProfile,
  GeographyOptionsResponse,
  StateGeographyOptionResponse,
} from '../types'

interface ScenarioFormProps {
  features: FeatureDefinition[]
  busy: boolean
  geographyOptions: GeographyOptionsResponse | null
  geographyLoading: boolean
  geographyError: string | null
}

type ProfileKey = 'baseline' | 'candidate'

const fieldMeta: Partial<
  Record<
    keyof FeatureProfile,
    {
      group: string
      shortLabel: string
      helper: string
      suffix?: string
    }
  >
> = {
  age: {
    group: 'Demographics',
    shortLabel: 'Years',
    helper: 'Age in years.',
    suffix: 'y',
  },
  bmi: {
    group: 'Body metrics',
    shortLabel: 'BMI',
    helper: 'Body mass index.',
  },
  smoker: {
    group: 'Substances',
    shortLabel: 'Smoking',
    helper: 'Smoking status.',
  },
  alcohol_servings_per_week: {
    group: 'Substances',
    shortLabel: 'Drinks per week',
    helper: 'Approximate drinks per week.',
  },
  exercise_minutes_per_week: {
    group: 'Activity',
    shortLabel: 'Minutes per week',
    helper: 'Exercise minutes per week.',
    suffix: 'min',
  },
  annual_aqi: {
    group: 'Environment',
    shortLabel: 'Annual AQI',
    helper: 'EPA annual AQI proxy.',
  },
  pm25_mean: {
    group: 'Environment',
    shortLabel: 'PM2.5',
    helper: 'EPA annual fine-particle mean.',
  },
  ozone_mean: {
    group: 'Environment',
    shortLabel: 'Ozone',
    helper: 'EPA annual ozone mean concentration.',
  },
}

const groupOrder = ['Demographics', 'Body metrics', 'Activity', 'Substances', 'Environment']
const defaultOpenGroups = ['Demographics', 'Body metrics', 'Activity']

function clamp(value: number, min: number | null, max: number | null): number {
  if (min != null && value < min) {
    return min
  }
  if (max != null && value > max) {
    return max
  }
  return value
}

function normalizeNumberInput(
  rawValue: string,
  feature: FeatureDefinition,
  fallback: number,
): number {
  if (rawValue.trim() === '') {
    return fallback
  }
  const parsed = Number(rawValue)
  if (!Number.isFinite(parsed)) {
    return fallback
  }

  const clamped = clamp(parsed, feature.min_value, feature.max_value)
  if (feature.step == null || feature.step <= 0) {
    return clamped
  }

  const stepBase = feature.min_value ?? 0
  const snapped =
    Math.round((clamped - stepBase) / feature.step) * feature.step + stepBase
  return clamp(Number(snapped.toFixed(6)), feature.min_value, feature.max_value)
}

function formatNumericValue(value: number, field: keyof FeatureProfile): string {
  const meta = fieldMeta[field]
  if (field === 'exercise_minutes_per_week') {
    return `${Math.round(value)} min`
  }
  if (field === 'age') {
    return `${Math.round(value)} years`
  }
  if (field === 'alcohol_servings_per_week') {
    return `${Math.round(value)} drinks`
  }
  if (field === 'annual_aqi') {
    return `${Math.round(value)} AQI`
  }
  if (field === 'pm25_mean') {
    return `${value.toFixed(1)} µg/m³`
  }
  if (field === 'ozone_mean') {
    return `${value.toFixed(3)} ppm`
  }
  if (field === 'bmi') {
    return value.toFixed(1)
  }
  if (meta?.suffix) {
    return `${value}${meta.suffix}`
  }
  return String(value)
}

function formatProfileValue(
  value: FeatureProfile[keyof FeatureProfile],
  field: keyof FeatureProfile,
): string {
  if (typeof value === 'boolean') {
    return value ? 'Yes' : 'No'
  }
  return formatNumericValue(Number(value), field)
}

function formatCandidateChange(
  field: keyof FeatureProfile,
  baseline: FeatureProfile,
  candidate: FeatureProfile,
): string | null {
  const currentValue = baseline[field]
  const candidateValue = candidate[field]
  if (currentValue === candidateValue) {
    return null
  }
  if (typeof currentValue === 'boolean' || typeof candidateValue === 'boolean') {
    return `${formatProfileValue(currentValue, field)} to ${formatProfileValue(candidateValue, field)}`
  }
  const delta = Number(candidateValue) - Number(currentValue)
  const sign = delta > 0 ? '+' : ''
  return `${sign}${formatProfileValue(delta, field)} vs current`
}

function groupedFeatures(features: FeatureDefinition[]): Array<[string, FeatureDefinition[]]> {
  const grouped = new Map<string, FeatureDefinition[]>()
  for (const feature of features) {
    const group = fieldMeta[feature.field]?.group ?? 'Other'
    const items = grouped.get(group) ?? []
    items.push(feature)
    grouped.set(group, items)
  }

  const orderedEntries: Array<[string, FeatureDefinition[]]> = []
  for (const group of groupOrder) {
    const items = grouped.get(group)
    if (items?.length) {
      orderedEntries.push([group, items])
    }
  }
  for (const [group, items] of grouped.entries()) {
    if (!groupOrder.includes(group)) {
      orderedEntries.push([group, items])
    }
  }
  return orderedEntries
}

function ProfileSection({
  profileKey,
  features,
  openGroups,
  onToggleGroup,
}: {
  profileKey: ProfileKey
  features: FeatureDefinition[]
  openGroups: Set<string>
  onToggleGroup: (group: string) => void
}): JSX.Element {
  const { state, dispatch } = useScenario()
  const profile = state[profileKey]
  const baseline = state.baseline
  const candidate = state.candidate
  const profileLabel = profileKey === 'baseline' ? 'Current' : 'What-if'
  const sectionTone = profileKey === 'baseline' ? 'profile-current' : 'profile-whatif'

  function updateNumber(
    field: keyof FeatureProfile,
    feature: FeatureDefinition,
    event: ChangeEvent<HTMLInputElement>,
  ): void {
    dispatch({
      type: 'setField',
      profile: profileKey,
      field,
      value: normalizeNumberInput(
        event.target.value,
        feature,
        Number(profile[field]),
      ),
    })
  }

  return (
    <section
      className={`control-panel ${sectionTone}`}
      data-testid={`profile-${profileKey}`}
    >
      <div className="control-panel-header">
        <div>
          <p className="section-kicker">{profileLabel}</p>
          <h2>{profileKey === 'baseline' ? 'Current profile' : 'What-if profile'}</h2>
        </div>
        <button
          className="ghost-button"
          onClick={() => dispatch({ type: 'resetProfile', profile: profileKey })}
          type="button"
        >
          Reset
        </button>
      </div>

      {groupedFeatures(features).map(([group, groupFeatures]) => (
        <details
          className="control-group"
          key={`${profileKey}-${group}`}
          open={openGroups.has(group)}
        >
          <summary
            className="control-group-summary"
            onClick={(event) => {
              event.preventDefault()
              onToggleGroup(group)
            }}
          >
            <h3>{group}</h3>
            <span className="control-group-count">
              {groupFeatures.length} {groupFeatures.length === 1 ? 'input' : 'inputs'}
            </span>
          </summary>
          <div className="control-stack">
            {groupFeatures.map((feature) => {
              const value = profile[feature.field]
              const meta = fieldMeta[feature.field]
              const fieldId = `${profileKey}-${feature.field}`
              const candidateChange =
                profileKey === 'candidate'
                  ? formatCandidateChange(feature.field, baseline, candidate)
                  : null
              return (
                <section
                  aria-labelledby={`${fieldId}-label`}
                  className={candidateChange ? 'control-field changed' : 'control-field'}
                  data-testid={
                    candidateChange ? `changed-input-${feature.field}` : undefined
                  }
                  key={`${profileKey}-${feature.field}`}
                >
                  <div className="control-field-header">
                    <div>
                      <span className="control-field-label" id={`${fieldId}-label`}>
                        {feature.label}
                      </span>
                      <p className="control-field-helper">{meta?.helper}</p>
                    </div>
                    {feature.kind === 'number' ? (
                      <strong className="control-field-value">
                        {formatNumericValue(Number(value), feature.field)}
                      </strong>
                    ) : (
                      <strong className="control-field-value">
                        {value ? 'Smoker' : 'No smoking'}
                      </strong>
                    )}
                  </div>
                  {candidateChange ? (
                    <p className="change-chip">
                      Changed: {candidateChange}
                    </p>
                  ) : null}

                  {feature.kind === 'boolean' ? (
                    <div className="toggle-group" role="group" aria-label={feature.label}>
                      <button
                        aria-pressed={!value}
                        className={!value ? 'toggle-button active' : 'toggle-button'}
                        onClick={() =>
                          dispatch({
                            type: 'setField',
                            profile: profileKey,
                            field: feature.field,
                            value: false,
                          })
                        }
                        type="button"
                      >
                        No
                      </button>
                      <button
                        aria-pressed={Boolean(value)}
                        className={value ? 'toggle-button active' : 'toggle-button'}
                        onClick={() =>
                          dispatch({
                            type: 'setField',
                            profile: profileKey,
                            field: feature.field,
                            value: true,
                          })
                        }
                        type="button"
                      >
                        Yes
                      </button>
                    </div>
                  ) : (
                    <div className="control-inputs">
                      <input
                        aria-label={`${profileLabel} ${feature.label} range input`}
                        max={feature.max_value ?? undefined}
                        min={feature.min_value ?? undefined}
                        onChange={(event) => updateNumber(feature.field, feature, event)}
                        step={feature.step ?? undefined}
                        type="range"
                        value={Number(value)}
                      />
                      <input
                        aria-label={`${profileLabel} ${feature.label} number input`}
                        max={feature.max_value ?? undefined}
                        min={feature.min_value ?? undefined}
                        onChange={(event) => updateNumber(feature.field, feature, event)}
                        step={feature.step ?? undefined}
                        type="number"
                        value={Number(value)}
                      />
                    </div>
                  )}
                </section>
              )
            })}
          </div>
        </details>
      ))}
    </section>
  )
}

function GeographyContextSection({
  geographyOptions,
  geographyLoading,
  geographyError,
}: {
  geographyOptions: GeographyOptionsResponse | null
  geographyLoading: boolean
  geographyError: string | null
}): JSX.Element {
  const { state, dispatch } = useScenario()
  const selectedGeography = state.geography
  const selectedOption = selectedGeography
    ? geographyOptions?.options.find(
        (option) =>
          option.state_fips === selectedGeography.state_fips &&
          option.year === selectedGeography.year,
      )
    : undefined
  const options = geographyOptions?.options ?? []
  const selectedValue = selectedGeography?.state_fips ?? ''
  const statusCopy = geographyError
    ? geographyError
    : geographyLoading
      ? 'Loading state-year context options.'
      : geographyOptions?.readiness.message ?? 'State-year context options are not loaded.'

  function setGeography(option: StateGeographyOptionResponse | undefined): void {
    dispatch({
      type: 'setGeography',
      geography: option
        ? {
            level: option.level,
            state_fips: option.state_fips,
            year: option.year,
          }
        : null,
    })
  }

  function handleStateChange(event: ChangeEvent<HTMLSelectElement>): void {
    setGeography(options.find((option) => option.state_fips === event.target.value))
  }

  return (
    <section className="geography-context-panel" data-testid="geography-context">
      <div className="geography-context-header">
        <div>
          <p className="section-kicker">Geography context</p>
          <h2>State-year background</h2>
        </div>
        <span
          className={
            geographyOptions?.readiness.active
              ? 'status-pill status-pill-ok'
              : 'status-pill status-pill-missing'
          }
        >
          {geographyOptions?.readiness.active ? 'Context ready' : 'Context inactive'}
        </span>
      </div>
      <p className="geography-context-copy">
        State context is background context for public state-year data, not a
        personal behavior like smoking, BMI, or activity.
      </p>
      <label className="context-select-label" htmlFor="geography-state-select">
        State context
      </label>
      <select
        aria-label="State context"
        className="context-select"
        disabled={geographyLoading || options.length === 0}
        id="geography-state-select"
        onChange={handleStateChange}
        value={selectedValue}
      >
        <option value="">Select a state</option>
        {options.map((option) => (
          <option key={`${option.year}-${option.state_fips}`} value={option.state_fips}>
            {option.label}
          </option>
        ))}
      </select>
      <div className="geography-context-status">
        <p data-testid="selected-geography-context">
          Selected: {selectedOption ? `${selectedOption.label} (${selectedOption.year})` : 'None'}
        </p>
        <p>{statusCopy}</p>
      </div>
    </section>
  )
}

export function ScenarioForm({
  features,
  busy,
  geographyOptions,
  geographyLoading,
  geographyError,
}: ScenarioFormProps): JSX.Element {
  const [openGroups, setOpenGroups] = useState<Set<string>>(
    () => new Set(defaultOpenGroups),
  )

  function toggleGroup(group: string): void {
    setOpenGroups((current) => {
      const next = new Set(current)
      if (next.has(group)) {
        next.delete(group)
      } else {
        next.add(group)
      }
      return next
    })
  }

  return (
    <aside className="scenario-form" data-testid="scenario-form">
      <div className="side-panel">
        <div className="side-panel-header">
          <div>
            <p className="section-kicker">Your lifestyle inputs</p>
            <h2>Compare current and what-if scenarios</h2>
          </div>
          <p className="side-panel-copy">
            Keep both profiles visible, adjust either side directly, and watch the explorer
            refresh live as the sliders move.
          </p>
        </div>

        <GeographyContextSection
          geographyError={geographyError}
          geographyLoading={geographyLoading}
          geographyOptions={geographyOptions}
        />

        <div className="toolbar toolbar-prominent live-toolbar" data-testid="live-update-status">
          <p className="toolbar-helper">
            {busy
              ? 'Updating the body map and drill-down from the current slider positions.'
              : 'Live preview is on. Drag any control to update the comparison.'}
          </p>
        </div>

        <div className="profile-grid">
          <ProfileSection
            features={features}
            onToggleGroup={toggleGroup}
            openGroups={openGroups}
            profileKey="baseline"
          />
          <ProfileSection
            features={features}
            onToggleGroup={toggleGroup}
            openGroups={openGroups}
            profileKey="candidate"
          />
        </div>
      </div>
    </aside>
  )
}
