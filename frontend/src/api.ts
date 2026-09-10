/**
 * The one place that knows where the API is and what it answers.
 *
 * `VITE_API_BASE` is `http://localhost:8000` in dev (`.env.development`) and `''` in the
 * build (`.env.production`), so the same code works cross-origin behind the Vite dev server
 * and same-origin behind FastAPI, with no edit. Everything goes **straight** to that base —
 * there is deliberately no dev proxy, because a proxied event stream is buffered and
 * arrives in one lump at the end of the run (`demo-spec.md` §10).
 */

import type {
  ProbeResult,
  RunCreated,
  RunSnapshot,
  UploadCreated,
} from './types'

export const API_BASE: string = import.meta.env.VITE_API_BASE ?? ''

/**
 * The replayer's query parameters (WI-2.3), threaded through from the browser URL.
 *
 * `?fixture=run-001` must work with **no backend run at all**, and it has to reach both the
 * snapshot and the event stream — the snapshot then answers `finished` with the report
 * attached, so the normal mount path needs no special case.
 */
export interface Replay {
  fixture?: string | null
  speed?: string | null
}

export class ApiError extends Error {
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

export function apiUrl(path: string, replay?: Replay): string {
  const url = new URL(`${API_BASE}${path}`, window.location.origin)
  if (replay?.fixture) url.searchParams.set('fixture', replay.fixture)
  if (replay?.speed) url.searchParams.set('speed', replay.speed)
  return url.toString()
}

/** The URL WI-2.4b points an `EventSource` at. Same base, same replay parameters. */
export function eventsUrl(runId: string, replay?: Replay): string {
  return apiUrl(`/api/runs/${encodeURIComponent(runId)}/events`, replay)
}

/**
 * FastAPI reports an `HTTPException` as `{detail: "…"}` and a validation failure as
 * `{detail: [{loc, msg, …}]}`. Both reach the user as one sentence rather than `[object
 * Object]`, which is what a naive `String(detail)` produces for the 422 that a missing
 * grant source raises — the most likely error anyone will actually see.
 */
async function failure(response: Response): Promise<ApiError> {
  let detail: unknown
  try {
    detail = (await response.json())?.detail
  } catch {
    detail = null
  }
  if (Array.isArray(detail)) {
    const messages = detail
      .map((item) => (typeof item?.msg === 'string' ? item.msg : null))
      .filter((m): m is string => m !== null)
    if (messages.length) return new ApiError(response.status, messages.join('; '))
  }
  if (typeof detail === 'string' && detail) return new ApiError(response.status, detail)
  return new ApiError(response.status, `${response.status} ${response.statusText}`)
}

async function json<T>(response: Response): Promise<T> {
  if (!response.ok) throw await failure(response)
  return (await response.json()) as T
}

export interface RunSources {
  grant_url?: string
  grant_upload_id?: string
  profile_url: string
}

/** ~10 s, zero LLM calls. Cached server-side by input hash, so pressing it twice is free. */
export async function probe(sources: RunSources, signal?: AbortSignal): Promise<ProbeResult> {
  const response = await fetch(apiUrl('/api/probe'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(sources),
    signal,
  })
  return json<ProbeResult>(response)
}

/** **201**, not 200 — and the body is `{run_id}`. */
export async function startRun(
  sources: RunSources,
  options: { probe_id?: string; answers?: Record<string, string> } = {},
  signal?: AbortSignal,
): Promise<RunCreated> {
  const response = await fetch(apiUrl('/api/runs'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ...sources, ...options }),
    signal,
  })
  return json<RunCreated>(response)
}

export async function fetchSnapshot(
  runId: string,
  replay?: Replay,
  signal?: AbortSignal,
): Promise<RunSnapshot> {
  const response = await fetch(apiUrl(`/api/runs/${encodeURIComponent(runId)}`, replay), {
    signal,
  })
  return json<RunSnapshot>(response)
}

/** PDF only, ≤25 MB — refused by magic bytes at the door, not by filename. */
export async function uploadGrant(file: File, signal?: AbortSignal): Promise<UploadCreated> {
  const body = new FormData()
  body.append('file', file)
  const response = await fetch(apiUrl('/api/uploads'), { method: 'POST', body, signal })
  return json<UploadCreated>(response)
}
