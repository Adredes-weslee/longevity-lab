import type {
  MetadataBootstrapResponse,
  ModelCardBundleResponse,
  PipelineStatusResponse,
  ScenarioCompareRequest,
  ScenarioCompareResponse,
} from '../types'

const API_PREFIX = '/api'
const API_BASE_URL = normalizeApiBaseUrl(import.meta.env.VITE_API_BASE_URL)

function normalizeApiBaseUrl(value: string | undefined): string {
  if (!value?.trim()) {
    return ''
  }
  const withScheme = ensureUrlScheme(value.trim())
  const withoutTrailingSlash = withScheme.replace(/\/+$/, '')
  return withoutTrailingSlash.endsWith(API_PREFIX)
    ? withoutTrailingSlash.slice(0, -API_PREFIX.length)
    : withoutTrailingSlash
}

function ensureUrlScheme(value: string): string {
  if (/^[a-z][a-z\d+\-.]*:\/\//i.test(value) || value.startsWith('/')) {
    return value
  }
  if (
    value.startsWith('localhost') ||
    value.startsWith('127.0.0.1') ||
    value.startsWith('[::1]')
  ) {
    return `http://${value}`
  }
  return `https://${value}`
}

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${API_PREFIX}${path}`, {
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

export async function fetchModelCards(): Promise<ModelCardBundleResponse> {
  return requestJson<ModelCardBundleResponse>('/models/cards')
}
