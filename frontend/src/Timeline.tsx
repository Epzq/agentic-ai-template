import Box from '@mui/material/Box'
import Chip from '@mui/material/Chip'
import CircularProgress from '@mui/material/CircularProgress'
import Stack from '@mui/material/Stack'
import Typography from '@mui/material/Typography'

import type { TimelineRow } from './timelineRows'

/**
 * Hand-rolled rather than `@mui/lab`'s `Timeline`.
 *
 * `@mui/lab` publishes only `9.0.0-beta.x` against MUI 9, and this is a rail, a dot and a
 * list. `demo-spec.md` §5 already made exactly this call once — rejecting the Pro-licensed
 * `@mui/x-charts` Heatmap for a hand-rolled grid, on the same reasoning. A beta dependency
 * pulled fresh by `npm ci` on the morning of the demo is not worth a vertical line.
 */

const DOT: Record<TimelineRow['severity'], string> = {
  normal: 'primary.main',
  warning: 'warning.main',
  error: 'error.main',
}

export function Timeline({ rows }: { rows: TimelineRow[] }) {
  if (rows.length === 0) {
    return (
      <Typography color="text.secondary" data-testid="timeline-empty">
        Waiting for the first event…
      </Typography>
    )
  }

  return (
    <Box data-testid="timeline" sx={{ position: 'relative', pl: 3 }}>
      {/* the rail */}
      <Box
        sx={{
          position: 'absolute',
          left: 6,
          top: 8,
          bottom: 8,
          width: '2px',
          bgcolor: 'divider',
        }}
      />
      {rows.map((row) => (
        <Box
          key={row.seq}
          data-testid="timeline-event"
          data-kind={row.kind}
          sx={{ position: 'relative', py: 0.75 }}
        >
          <Box
            sx={{
              position: 'absolute',
              left: -21,
              top: 12,
              width: 10,
              height: 10,
              borderRadius: '50%',
              bgcolor: DOT[row.severity],
              outline: '2px solid',
              outlineColor: 'background.default',
            }}
          />
          <Stack direction="row" spacing={1} sx={{ alignItems: 'baseline', flexWrap: 'wrap' }}>
            <Typography
              variant="body2"
              sx={{ fontWeight: row.kind === 'stage' ? 600 : 400 }}
              data-testid="timeline-label"
            >
              {row.label}
            </Typography>
            {row.running && <CircularProgress size={12} data-testid="timeline-running" />}
            {row.ms !== null && (
              <Typography variant="caption" color="text.secondary">
                {formatMs(row.ms)}
              </Typography>
            )}
            {row.sources > 0 && (
              <Chip
                size="small"
                variant="outlined"
                label={`+${row.sources}`}
                data-testid="timeline-sources"
              />
            )}
          </Stack>
          {row.detail && (
            <Typography variant="caption" color="text.secondary" sx={{ display: 'block' }}>
              {row.detail}
            </Typography>
          )}
        </Box>
      ))}
    </Box>
  )
}

function formatMs(ms: number): string {
  return ms >= 1000 ? `${(ms / 1000).toFixed(1)}s` : `${ms}ms`
}
