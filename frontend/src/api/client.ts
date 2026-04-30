import type {
  MetadataBootstrapResponse,
  PipelineStatusResponse,
  ScenarioCompareRequest,
  ScenarioCompareResponse,
} from '../types'

const API_PREFIX = '/api'

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_PREFIX}${path}`, {
    headers: {
      'Content-Type': 'application/json',
      ...(init?.headers ?? {}),
    },
    ...init,
  })

  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`)
  }

  return (await response.json()) as T
}

export async function fetchBootstrap(): Promise<MetadataBootstrapResponse> {
  return requestJson<MetadataBootstrapResponse>('/metadata/bootstrap')
}

export async function compareScenarios(
  payload: ScenarioCompareRequest,
): Promise<ScenarioCompareResponse> {
  return requestJson<ScenarioCompareResponse>('/scenario/compare', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export async function fetchPipelineStatus(
  year = 2023,
): Promise<PipelineStatusResponse> {
  return requestJson<PipelineStatusResponse>(`/pipeline/status?year=${year}`)
}
