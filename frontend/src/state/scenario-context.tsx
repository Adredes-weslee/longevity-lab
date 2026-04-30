import {
  createContext,
  useContext,
  useMemo,
  useReducer,
  type Dispatch,
  type JSX,
  type PropsWithChildren,
} from 'react'

import type { FeatureProfile } from '../types'

type ProfileKey = 'baseline' | 'candidate'
type ProfileField = keyof FeatureProfile

interface ScenarioState {
  baseline: FeatureProfile
  candidate: FeatureProfile
  selectedOrganId: string | null
}

type ScenarioAction =
  | {
      type: 'setField'
      profile: ProfileKey
      field: ProfileField
      value: FeatureProfile[ProfileField]
    }
  | { type: 'resetProfile'; profile: ProfileKey }
  | { type: 'selectOrgan'; organId: string | null }

interface ScenarioContextValue {
  state: ScenarioState
  dispatch: Dispatch<ScenarioAction>
}

export const defaultBaseline: FeatureProfile = {
  age: 45,
  bmi: 28,
  smoker: true,
  alcohol_servings_per_week: 10,
  exercise_minutes_per_week: 60,
  annual_aqi: 80,
}

export const defaultCandidate: FeatureProfile = {
  age: 45,
  bmi: 26,
  smoker: false,
  alcohol_servings_per_week: 4,
  exercise_minutes_per_week: 180,
  annual_aqi: 55,
}

const ScenarioContext = createContext<ScenarioContextValue | undefined>(undefined)

function scenarioReducer(
  state: ScenarioState,
  action: ScenarioAction,
): ScenarioState {
  switch (action.type) {
    case 'setField':
      return {
        ...state,
        [action.profile]: {
          ...state[action.profile],
          [action.field]: action.value,
        },
      }
    case 'resetProfile':
      return {
        ...state,
        [action.profile]:
          action.profile === 'baseline' ? defaultBaseline : defaultCandidate,
      }
    case 'selectOrgan':
      return {
        ...state,
        selectedOrganId: action.organId,
      }
    default:
      return state
  }
}

export function ScenarioProvider({
  children,
}: PropsWithChildren): JSX.Element {
  const [state, dispatch] = useReducer(scenarioReducer, {
    baseline: defaultBaseline,
    candidate: defaultCandidate,
    selectedOrganId: 'heart',
  })

  const value = useMemo(
    () => ({ state, dispatch }),
    [state],
  )

  return (
    <ScenarioContext.Provider value={value}>
      {children}
    </ScenarioContext.Provider>
  )
}

export function useScenario(): ScenarioContextValue {
  const context = useContext(ScenarioContext)
  if (!context) {
    throw new Error('useScenario must be used inside ScenarioProvider')
  }
  return context
}
