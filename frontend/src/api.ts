import { readSSEStream } from './lib/sse'
import { parseActivitySnapshot, writeCachedActivity } from './activity'
import type { ActivitySnapshot } from './activity'
import type { HistoryItem, PlaygroundConfig, StreamEvent } from './types'

const rawApiUrl = import.meta.env.VITE_API_URL?.trim()

export class ApiError extends Error {
  readonly status: number
  readonly retryAfter?: number

  constructor(message: string, status: number, retryAfter?: number) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.retryAfter = retryAfter
  }
}

function apiUrl(path: string): string {
  if (!rawApiUrl) {
    throw new ApiError('The API URL is not configured for this deployment.', 0)
  }
  return `${rawApiUrl.replace(/\/$/, '')}${path}`
}

async function errorFromResponse(response: Response): Promise<ApiError> {
  const retryHeader = response.headers.get('Retry-After')
  const retryAfter = retryHeader ? Number.parseInt(retryHeader, 10) : undefined
  let detail = ''

  try {
    const body = (await response.json()) as { detail?: unknown }
    if (typeof body.detail === 'string') detail = body.detail
  } catch {
    // The status-specific copy below is safer than leaking an upstream body.
  }

  if (response.status === 429) {
    const wait = retryAfter && Number.isFinite(retryAfter) ? formatWait(retryAfter) : 'later'
    return new ApiError(`This demo's shared usage limit has been reached. Please try again ${wait}.`, 429, retryAfter)
  }
  if (response.status === 422) {
    return new ApiError('That request could not be validated. Shorten the question and try again.', 422)
  }
  if (response.status >= 500) {
    return new ApiError('The retrieval service is temporarily unavailable. Please try again shortly.', response.status)
  }
  return new ApiError(detail || `The request failed with status ${response.status}.`, response.status)
}

function formatWait(seconds: number): string {
  if (seconds < 60) return `in ${seconds} seconds`
  if (seconds < 3600) return `in about ${Math.ceil(seconds / 60)} minutes`
  if (seconds < 86_400) return `in about ${Math.ceil(seconds / 3600)} hours`
  return `in about ${Math.ceil(seconds / 86_400)} days`
}

export async function getConfig(signal?: AbortSignal): Promise<PlaygroundConfig> {
  let response: Response
  try {
    response = await fetch(apiUrl('/v1/config'), {
      method: 'GET',
      headers: { Accept: 'application/json' },
      signal,
    })
  } catch (error) {
    if (error instanceof ApiError || (error instanceof DOMException && error.name === 'AbortError')) throw error
    throw new ApiError('Could not reach the retrieval service. Check your connection and retry.', 0)
  }

  if (!response.ok) throw await errorFromResponse(response)
  const config = (await response.json()) as PlaygroundConfig
  if (!config.embedders?.length || !config.llms?.length) {
    throw new ApiError('The retrieval service returned an incomplete model configuration.', 0)
  }
  return config
}

export async function getActivity(signal?: AbortSignal): Promise<ActivitySnapshot> {
  let response: Response
  try {
    response = await fetch(apiUrl('/v1/activity'), {
      method: 'GET',
      headers: { Accept: 'application/json' },
      credentials: 'omit',
      cache: 'no-cache',
      signal,
    })
  } catch (error) {
    if (error instanceof ApiError || (error instanceof DOMException && error.name === 'AbortError')) throw error
    throw new ApiError('Could not refresh activity data.', 0)
  }

  if (!response.ok) throw await errorFromResponse(response)
  const activity = parseActivitySnapshot(await response.json())
  if (!activity) throw new ApiError('The activity service returned an invalid response.', 0)
  writeCachedActivity(activity)
  return activity
}

type ChatInput = {
  question: string
  embedder: string
  model: string
  history: HistoryItem[]
  topK: number
  useHistory: boolean
}

export async function streamChat(
  input: ChatInput,
  onEvent: (event: StreamEvent) => void,
  signal: AbortSignal,
): Promise<void> {
  let response: Response
  try {
    response = await fetch(apiUrl('/v1/chat'), {
      method: 'POST',
      headers: {
        Accept: 'text/event-stream',
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(input),
      signal,
    })
  } catch (error) {
    if (error instanceof ApiError || (error instanceof DOMException && error.name === 'AbortError')) throw error
    throw new ApiError('The connection to the retrieval service was interrupted.', 0)
  }

  if (!response.ok) throw await errorFromResponse(response)
  if (!response.body) throw new ApiError('This browser could not open the answer stream.', 0)
  await readSSEStream(response.body, onEvent)
}
