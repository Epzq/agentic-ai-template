import Box from '@mui/material/Box'
import Paper from '@mui/material/Paper'
import Tooltip from '@mui/material/Tooltip'
import Typography from '@mui/material/Typography'

import { CRITERIA, label, type Ranked } from '../ranking'
import type { Direction } from '../types'

/**
 * 3 directions × 9 criteria = 27 cells, as a plain CSS grid.
 *
 * ⚠️ **Not `@mui/x-charts`' Heatmap** — that is a Pro-licensed component, verified on
 * mui.com. `demo-spec.md` §5 calls for exactly this instead: a grid of boxes with a
 * single-hue scale and a tooltip per cell. No dependency, no licence, and the two
 * never-scored columns can render "not assessed" rather than a misleading zero.
 *
 * It takes the **ranked** directions, not `report.directions`. It used to take the latter
 * and label each column with `direction.rank` — the rank the backend stored — while the
 * cards below it used the rank recomputed in the browser. So the first slider move put a
 * column headed "#1" above a card headed "#1" that was a different direction, on the one
 * screen whose whole job is to let you compare the two.
 */

/** A single hue, lightness only. A rainbow scale would imply categories that do not exist. */
function shade(value: number): string {
  // 0..10 -> 0.08..0.85 alpha of the primary hue.
  const alpha = 0.08 + (Math.max(0, Math.min(10, value)) / 10) * 0.77
  return `rgba(27, 94, 111, ${alpha.toFixed(2)})`
}

export function ScoreMatrix({ directions }: { directions: readonly Ranked<Direction>[] }) {
  return (
    <Paper variant="outlined" sx={{ p: 3, overflowX: 'auto' }} data-testid="score-matrix">
      <Typography variant="h6" gutterBottom>
        Score matrix
      </Typography>
      <Box
        sx={{
          display: 'grid',
          gridTemplateColumns: `minmax(190px, auto) repeat(${directions.length}, minmax(84px, 1fr))`,
          gap: '2px',
          minWidth: 420,
        }}
      >
        <Box />
        {directions.map(({ item, rank }) => (
          <Box key={item.title} sx={{ px: 1, pb: 1 }}>
            <Typography variant="caption" color="text.secondary" noWrap title={item.title}>
              #{rank}
            </Typography>
          </Box>
        ))}

        {CRITERIA.map((criterion) => (
          <Box key={criterion} sx={{ display: 'contents' }}>
            <Box sx={{ pr: 1, py: 0.75 }}>
              <Typography variant="body2">{label(criterion)}</Typography>
            </Box>
            {directions.map(({ item: direction }) => {
              const score = direction.scores[criterion] ?? null
              if (score === null) {
                return (
                  <Box
                    key={`${criterion}-${direction.title}`}
                    data-testid="matrix-cell"
                    data-criterion={criterion}
                    data-assessed="false"
                    sx={{
                      display: 'grid',
                      placeItems: 'center',
                      bgcolor: 'action.hover',
                      color: 'text.disabled',
                      borderRadius: 0.5,
                      py: 0.75,
                    }}
                  >
                    <Typography variant="caption">n/a</Typography>
                  </Box>
                )
              }
              return (
                <Tooltip
                  key={`${criterion}-${direction.title}`}
                  title={`${label(criterion)} · ${score.value.toFixed(1)} — ${score.rationale}`}
                >
                  <Box
                    data-testid="matrix-cell"
                    data-criterion={criterion}
                    data-assessed="true"
                    data-value={score.value}
                    sx={{
                      display: 'grid',
                      placeItems: 'center',
                      bgcolor: shade(score.value),
                      color: score.value >= 6 ? 'common.white' : 'text.primary',
                      borderRadius: 0.5,
                      py: 0.75,
                    }}
                  >
                    <Typography variant="caption" sx={{ fontWeight: 600 }}>
                      {score.value.toFixed(1)}
                    </Typography>
                  </Box>
                </Tooltip>
              )
            })}
          </Box>
        ))}
      </Box>
      <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 1.5 }}>
        Two criteria are never scored in this build — the competitor and collaborator stage is
        out of scope, so they are excluded from the weighted mean rather than counted as zero.
      </Typography>
    </Paper>
  )
}
