import Alert from '@mui/material/Alert'
import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import Chip from '@mui/material/Chip'
import CircularProgress from '@mui/material/CircularProgress'
import Paper from '@mui/material/Paper'
import Stack from '@mui/material/Stack'
import Typography from '@mui/material/Typography'
import { useEffect, useState } from 'react'
import { useParams, useSearchParams } from 'react-router'

import { ApiError, fetchSnapshot } from '../api'
import { ReportView } from '../report/ReportView'
import { Timeline } from '../Timeline'
import { Warnings } from '../Warnings'
import { sourceCount, toTimeline } from '../timelineRows'
import type { RunEvent, RunSnapshot, RunStatus } from '../types'
import { useRunStream } from '../useRunStream'

const STATUS_COLOUR: Record<RunStatus, 'info' | 'success' | 'error'> = {
  running: 'info',
  finished: 'success',
  failed: 'error',
}

/**
 * The run's own page. **The run id is in the URL**, so a refresh mid-run comes back here and
 * re-reads the snapshot rather than starting over — that is AC8b, and it is why the id is a
 * route parameter rather than component state.
 *
 * `?fixture=run-001` (and optional `&speed=`) are passed straight through to the API. The
 * snapshot then answers `finished` with the report attached and no run has to exist, which
 * is both the frontend iteration loop and the demo-day fallback (WI-2.3).
 *
 * There is deliberately **no polling** — but the snapshot is fetched **twice**: once on
 * mount, and once more the moment the stream reports a terminal event.
 *
 * 🐛 That second fetch is not an optimisation, it is the difference between a working demo
 * and a broken one. `status` and the **report** live only on the snapshot; the stream carries
 * events. Fetch once and a live run finishes with the timeline full, the status chip still
 * reading "running", and **no report on the page at all** — AC1's "pressing Run produces a
 * rendered report" quietly false. Found by the AC9 browser test, which was the first thing to
 * drive a whole run through the UI.
 *
 * AC7's "remains visible after completion" is free either way: the timeline is ordinary
 * state, and the stream closing does not clear it.
 */
export default function RunPage() {
  const { runId = '' } = useParams()
  const [params] = useSearchParams()
  const replay = { fixture: params.get('fixture'), speed: params.get('speed') }

  const [snapshot, setSnapshot] = useState<RunSnapshot | null>(null)
  const [error, setError] = useState<string | null>(null)
  const stream = useRunStream(runId, replay)

  const { fixture, speed } = replay
  useEffect(() => {
    // StrictMode mounts effects twice in dev, and the parameters can change under us; the
    // abort is what keeps a stale response from overwriting a fresher one. Nothing is set
    // synchronously here — that would only cause a second render before the fetch resolves.
    const controller = new AbortController()
    // `stream.done` is in the dependency list on purpose: flipping it re-runs this effect,
    // which is the one re-fetch that picks up the finished status and the report.
    fetchSnapshot(runId, { fixture, speed }, controller.signal)
      .then((next) => {
        if (controller.signal.aborted) return
        setSnapshot(next)
        setError(null)
      })
      .catch((cause: unknown) => {
        if (controller.signal.aborted) return
        setError(cause instanceof ApiError ? cause.message : String(cause))
      })
    return () => controller.abort()
  }, [runId, fixture, speed, stream.done])

  if (error) {
    return (
      <Alert severity="error" data-testid="run-error">
        {error}
      </Alert>
    )
  }

  if (!snapshot) {
    return (
      <Stack direction="row" spacing={2} sx={{ alignItems: 'center' }} data-testid="run-loading">
        <CircularProgress size={20} />
        <Typography color="text.secondary">Loading {runId}…</Typography>
      </Stack>
    )
  }

  // The stream replays from seq 0 on every connection, so it is authoritative once it has
  // said anything; the snapshot covers the moment before the first frame arrives and the
  // case where the stream cannot be opened at all.
  const events: RunEvent[] = stream.events.length ? stream.events : snapshot.events
  const rows = toTimeline(events)

  return (
    <Stack spacing={3}>
      <Box>
        <Stack direction="row" spacing={2} sx={{ alignItems: 'center' }}>
          <Typography variant="h4" data-testid="run-id">
            {snapshot.run_id}
          </Typography>
          <Chip
            label={snapshot.status}
            color={STATUS_COLOUR[snapshot.status]}
            data-testid="run-status"
          />
          {fixture && <Chip label={`replay: ${fixture}`} variant="outlined" size="small" />}
        </Stack>
        <Typography color="text.secondary" sx={{ mt: 1 }}>
          {snapshot.inputs.grant_src} · {snapshot.inputs.profile_url}
        </Typography>
      </Box>

      <Warnings events={events} />

      <Paper variant="outlined" sx={{ p: 3 }}>
        <Stack
          direction="row"
          spacing={2}
          sx={{ alignItems: 'center', justifyContent: 'space-between', mb: 2 }}
        >
          <Typography variant="h6">Activity</Typography>
          <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
            {stream.connected && <CircularProgress size={14} data-testid="stream-live" />}
            <Chip
              size="small"
              label={`Sources (${sourceCount(events)})`}
              data-testid="sources-count"
            />
            <Typography variant="caption" color="text.secondary" data-testid="event-count">
              {events.length} events
            </Typography>
          </Stack>
        </Stack>

        {stream.error && (
          <Alert severity="warning" sx={{ mb: 2 }} data-testid="stream-error">
            {stream.error}
          </Alert>
        )}

        <Timeline rows={rows} />
      </Paper>

      {snapshot.report && <ReportView report={snapshot.report} />}

      <Box>
        <Button href="/" data-testid="back-to-form">
          Analyse another call
        </Button>
      </Box>
    </Stack>
  )
}
