/**
 * Turn the raw event log into the rows a person reads.
 *
 * Two decisions worth knowing.
 *
 * **`started` and `finished` are collapsed into one row.** The recorded run emits 25
 * `tool.started` + 25 `tool.finished` + 10 of each `stage.*`; rendered raw that is 70 rows
 * saying the same 35 things twice. One row per step — starting as "running", gaining its
 * duration when the matching `finished` arrives — is shorter *and* more informative, because
 * you can see what is happening right now.
 *
 * **`evidence.added` is not a row.** 85 of the 162 events are evidence, and listing them
 * would bury the activity they belong to. They feed the "Sources (N)" counter, and each
 * tool's row names how many it minted. WI-2.5 renders the rows themselves as chips.
 *
 * Separate from `Timeline.tsx` on purpose, and not named `timeline.ts`: that would differ
 * from the component only in casing, which `tsc` rejects outright and which a
 * case-sensitive filesystem would resolve as two different files.
 */

import type { RunEvent } from './types'

/**
 * Hand-rolled rather than `@mui/lab`'s `Timeline`.
 *
 * `@mui/lab` publishes only `9.0.0-beta.x` against MUI 9, and this is a rail, a dot and a
 * list — `demo-spec.md` §5 already made exactly this call once, rejecting the Pro-licensed
 * `@mui/x-charts` Heatmap for a hand-rolled grid on the same reasoning. A beta dependency
 * pulled fresh by `npm ci` on the morning of the demo is not worth a vertical line.
 *
 * The reduction from raw events to rows lives here too rather than in a `timeline.ts`: on a
 * case-insensitive filesystem that pair differs only in casing, which `tsc` rejects and a
 * Linux checkout would resolve differently.
 */


export type StepKind = 'stage' | 'tool' | 'note'

export interface TimelineRow {
  /** The `seq` of the event that opened this row — stable, and unique. */
  seq: number
  kind: StepKind
  label: string
  detail: string
  /** Elapsed ms, once the matching `finished` arrived. */
  ms: number | null
  running: boolean
  /** How many evidence rows this step minted. */
  sources: number
  severity: 'normal' | 'warning' | 'error'
}

function text(value: unknown, fallback = ''): string {
  return typeof value === 'string' && value ? value : fallback
}

function count(value: unknown): number {
  return Array.isArray(value) ? value.length : 0
}

/**
 * Close the most recent still-open row with this name. The pipeline is strictly
 * sequential, so "most recent open" is unambiguous — `search_literature` runs nine times
 * and each `finished` belongs to the one immediately before it.
 */
function closeMatching(rows: TimelineRow[], kind: StepKind, label: string, event: RunEvent) {
  for (let i = rows.length - 1; i >= 0; i -= 1) {
    const row = rows[i]
    if (row.running && row.kind === kind && row.label === label) {
      row.running = false
      row.ms = typeof event.ms === 'number' ? event.ms : null
      row.sources = count(event.evidence_added)
      if (text(event.summary)) row.detail = text(event.summary)
      return
    }
  }
}

export function toTimeline(events: RunEvent[]): TimelineRow[] {
  const rows: TimelineRow[] = []

  for (const event of events) {
    switch (event.type) {
      case 'run.started':
        rows.push({
          seq: event.seq, kind: 'note', label: 'Run started',
          detail: '', ms: null, running: false, sources: 0, severity: 'normal',
        })
        break

      case 'stage.started':
        rows.push({
          seq: event.seq, kind: 'stage', label: text(event.stage, 'stage'),
          detail: '', ms: null, running: true, sources: 0, severity: 'normal',
        })
        break

      case 'stage.finished':
        closeMatching(rows, 'stage', text(event.stage, 'stage'), event)
        break

      case 'tool.started':
        rows.push({
          seq: event.seq, kind: 'tool', label: text(event.tool, 'tool'),
          detail: text(event.args_summary), ms: null, running: true,
          sources: 0, severity: 'normal',
        })
        break

      case 'tool.finished':
        closeMatching(rows, 'tool', text(event.tool, 'tool'), event)
        break

      case 'identity.resolved':
        rows.push({
          seq: event.seq, kind: 'note', label: 'Author resolved',
          detail: `${text(event.display_name, 'unknown')} — ${text(event.confidence, 'unverified')}`,
          ms: null, running: false, sources: 0, severity: 'normal',
        })
        break

      case 'warning':
        rows.push({
          seq: event.seq, kind: 'note', label: text(event.code, 'warning'),
          detail: text(event.message), ms: null, running: false,
          sources: 0, severity: 'warning',
        })
        break

      case 'run.finished':
        rows.push({
          seq: event.seq, kind: 'note', label: 'Run finished',
          detail: '', ms: null, running: false, sources: 0, severity: 'normal',
        })
        break

      case 'run.failed':
        rows.push({
          seq: event.seq, kind: 'note', label: text(event.code, 'run failed'),
          detail: text(event.message), ms: null, running: false,
          sources: 0, severity: 'error',
        })
        break

      // evidence.added deliberately produces no row — see the module docstring.
      default:
        break
    }
  }
  return rows
}

/** AC7's "Sources (N)": every evidence row the run has minted so far. */
export function sourceCount(events: RunEvent[]): number {
  return events.reduce((total, event) => total + (event.type === 'evidence.added' ? 1 : 0), 0)
}
