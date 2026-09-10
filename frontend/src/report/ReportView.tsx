import Chip from '@mui/material/Chip'
import Stack from '@mui/material/Stack'
import Typography from '@mui/material/Typography'
import { useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'react-router'

import {
  DEFAULT_WEIGHTS,
  decodeWeights,
  encodeWeights,
  isDefault,
  rankBy,
  type Weights,
} from '../ranking'
import type { Evidence, Report } from '../types'
import { DirectionCard } from './DirectionCard'
import { EvidencePanel } from './EvidencePanel'
import { IdentityBanner } from './IdentityBanner'
import { ScoreMatrix } from './ScoreMatrix'
import { WeightSliders } from './WeightSliders'

/**
 * The report (AC2, AC3, AC6, AC11).
 *
 * **The weights live in the URL, and are the only state here that leaves the component.**
 * `replace: true` on the navigation keeps a drag from filling the back button with one entry
 * per pixel, and it means a particular view of the report — "look at this with novelty
 * turned up" — is a link someone can paste.
 *
 * Re-ranking is `useMemo` over data already in the browser: no fetch, no effect, nothing to
 * await. That is what makes AC6's "< 100 ms with zero network requests" true by construction
 * rather than by optimisation.
 */
export function ReportView({ report }: { report: Report }) {
  const [params, setParams] = useSearchParams()
  const [open, setOpen] = useState<Evidence | null>(null)

  /**
   * 🐛 **React state is the truth; the URL is a mirror.** The obvious shape — derive the
   * weights from `?w=` and write back on every change — silently drops rapid updates:
   * router navigation is asynchronous, so nine slider changes in quick succession all read
   * the same committed URL and only the last one survives. On a demo that looks like the
   * slider snapping back, with nothing in the console. The AC6 test, which moves all nine,
   * is what caught it.
   *
   * The ref is what makes a burst compose: it advances synchronously, so each change builds
   * on the previous one rather than on the last render.
   */
  const [weights, setWeights] = useState<Weights>(() => decodeWeights(params.get('w')))
  const latest = useRef(weights)

  const byId = useMemo(
    () => new Map(report.evidence.map((record) => [record.id, record])),
    [report.evidence],
  )
  const ranked = useMemo(() => rankBy(report.directions, weights), [report.directions, weights])

  function updateWeights(change: (current: Weights) => Weights) {
    const next = change(latest.current)
    latest.current = next
    setWeights(next)
    // The URL follows. `replace` keeps a drag from filling the back button with one entry
    // per pixel, and a URL that lags a frame behind the render costs nothing.
    setParams(
      (previous) => {
        const updated = new URLSearchParams(previous)
        if (isDefault(next)) updated.delete('w')
        else updated.set('w', encodeWeights(next))
        return updated
      },
      { replace: true },
    )
  }

  const papers = report.evidence.filter((record) => record.source_type === 'paper').length

  return (
    <Stack spacing={3}>
      <IdentityBanner identity={report.identity} />

      <Stack direction="row" spacing={1} sx={{ alignItems: 'center', flexWrap: 'wrap', gap: 1 }}>
        <Typography variant="h5">
          {report.directions.length} ranked directions
        </Typography>
        <Chip size="small" variant="outlined" label={`${report.evidence.length} evidence rows`} />
        <Chip
          size="small"
          variant="outlined"
          label={`${papers} papers`}
          data-testid="paper-count"
        />
      </Stack>

      <WeightSliders
        weights={weights}
        onChange={(criterion, value) =>
          updateWeights((current) => ({ ...current, [criterion]: value }))
        }
        onReset={() => updateWeights(() => DEFAULT_WEIGHTS)}
      />

      <ScoreMatrix directions={ranked} />

      {ranked.map(({ item, overall, rank }) => (
        <DirectionCard
          key={item.title}
          direction={item}
          rank={rank}
          overall={overall}
          byId={byId}
          onOpen={setOpen}
        />
      ))}

      <EvidencePanel record={open} onClose={() => setOpen(null)} />
    </Stack>
  )
}
