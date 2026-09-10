/**
 * The live activity timeline (AC7).
 *
 * Four things here are load-bearing, and every one of them was learned the hard way in
 * WI-2.2 — see that item's STATUS before changing any of them.
 *
 * 1. **`es.close()` is not optional.** The server ends the stream itself after
 *    `run.finished`, and an `EventSource` treats a server-closed connection as a *dropped*
 *    one: it reconnects after ~3 s, replays all 162 events, and does it again, forever.
 *    Closing client-side is the only thing that stops the loop.
 * 2. **`onmessage`, not `addEventListener(type)`.** The server sets no `event:` name, on
 *    purpose — a named SSE event never reaches `onmessage`. The event's kind is the `type`
 *    field *inside* the JSON.
 * 3. **Every connection replays from seq 0.** `Last-Event-ID` is ignored by design, because
 *    AC8a is "replay all prior events to a newly-opened stream". Dedupe on `seq` is what
 *    makes that harmless — and what makes a mid-run browser refresh restore the timeline
 *    instead of doubling it.
 * 4. **The stream is the only source of timeline events.** Because it always replays from
 *    zero, there is nothing to seed from the snapshot; seeding would just be a second path
 *    to keep correct.
 */

import { useEffect, useState } from 'react'

import { eventsUrl, type Replay } from './api'
import type { RunEvent } from './types'

/** The two events after which the server sends nothing more. */
const TERMINAL = new Set(['run.finished', 'run.failed'])

export interface RunStream {
  /** Deduped and ordered by `seq`. */
  events: RunEvent[]
  /** The stream is open. False before the first event and after the run ends. */
  connected: boolean
  /** A terminal event arrived, so the timeline is complete. */
  done: boolean
  error: string | null
}

export function useRunStream(runId: string, replay?: Replay): RunStream {
  const [events, setEvents] = useState<RunEvent[]>([])
  const [connected, setConnected] = useState(false)
  const [done, setDone] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const fixture = replay?.fixture ?? null
  const speed = replay?.speed ?? null

  // Reset when the stream identity changes. Adjusting state during render rather than in an
  // effect is React's own recommendation for this: an effect would render the new run's page
  // once with the previous run's timeline still on it.
  const identity = `${runId}|${fixture}|${speed}`
  const [streaming, setStreaming] = useState(identity)
  if (streaming !== identity) {
    setStreaming(identity)
    setEvents([])
    setConnected(false)
    setDone(false)
    setError(null)
  }

  useEffect(() => {
    if (!runId) return
    const seen = new Set<number>()
    const source = new EventSource(eventsUrl(runId, { fixture, speed }))
    //: Set before `close()` so `onerror` can tell "the run ended" from "the socket broke".
    let finished = false

    source.onopen = () => {
      setConnected(true)
      setError(null)
    }

    source.onmessage = (message: MessageEvent<string>) => {
      let event: RunEvent
      try {
        event = JSON.parse(message.data) as RunEvent
      } catch {
        // One malformed frame must not take down a timeline that is otherwise fine.
        return
      }
      if (seen.has(event.seq)) return
      seen.add(event.seq)
      setEvents((prior) => [...prior, event].sort((a, b) => a.seq - b.seq))

      if (TERMINAL.has(event.type)) {
        finished = true
        source.close()
        setConnected(false)
        setDone(true)
      }
    }

    source.onerror = () => {
      setConnected(false)
      if (finished) return
      // EventSource reconnects on its own unless it has been closed, so this is a notice
      // rather than a failure — the run keeps going and the next connection replays from 0.
      if (source.readyState === EventSource.CLOSED) {
        setError('The connection to the run was lost.')
      }
    }

    return () => {
      source.close()
      setConnected(false)
    }
  }, [runId, fixture, speed])

  return { events, connected, done, error }
}
