import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import Paper from '@mui/material/Paper'
import Slider from '@mui/material/Slider'
import Stack from '@mui/material/Stack'
import Typography from '@mui/material/Typography'

import {
  CRITERIA,
  isDefault,
  label,
  NOT_ASSESSED,
  WEIGHT_MAX,
  WEIGHT_MIN,
  type Weights,
} from '../ranking'

/**
 * Nine sliders that re-rank the cards in the browser (AC6).
 *
 * Every one of the nine criteria gets a slider, **including the two that are never scored**.
 * Moving those changes nothing, which is the truth and is better shown than hidden — the
 * label says so rather than leaving someone to wonder why the cards did not move.
 *
 * Integer steps, and the absolute scale does not matter: the formula renormalises over the
 * criteria that were actually scored, so all-fives and all-ones give the same ranking.
 */
export function WeightSliders({
  weights,
  onChange,
  onReset,
}: {
  weights: Weights
  onChange: (criterion: string, value: number) => void
  onReset: () => void
}) {
  return (
    <Paper variant="outlined" sx={{ p: 3 }} data-testid="weight-sliders">
      <Stack
        direction="row"
        spacing={2}
        sx={{ alignItems: 'center', justifyContent: 'space-between', mb: 1 }}
      >
        <Box>
          <Typography variant="h6">Weights</Typography>
          <Typography variant="caption" color="text.secondary">
            Re-ranks in the browser. Nothing is sent anywhere, and the weights are in the URL.
          </Typography>
        </Box>
        <Button
          size="small"
          onClick={onReset}
          disabled={isDefault(weights)}
          data-testid="reset-weights"
        >
          Reset to default
        </Button>
      </Stack>

      {CRITERIA.map((criterion) => {
        const unscored = NOT_ASSESSED.includes(criterion)
        return (
          <Stack
            key={criterion}
            direction="row"
            spacing={2}
            sx={{ alignItems: 'center', opacity: unscored ? 0.55 : 1 }}
          >
            <Typography variant="body2" sx={{ minWidth: 210 }}>
              {label(criterion)}
              {unscored && (
                <Typography component="span" variant="caption" color="text.secondary">
                  {' '}
                  · not assessed
                </Typography>
              )}
            </Typography>
            <Slider
              size="small"
              min={WEIGHT_MIN}
              max={WEIGHT_MAX}
              step={1}
              value={weights[criterion] ?? 0}
              onChange={(_, value) => onChange(criterion, value as number)}
              valueLabelDisplay="auto"
              data-testid={`weight-slider-${criterion}`}
              slotProps={{
                input: {
                  'data-testid': `weight-input-${criterion}`,
                  'aria-label': label(criterion),
                } as React.InputHTMLAttributes<HTMLInputElement>,
              }}
              sx={{ maxWidth: 320 }}
            />
            <Typography variant="body2" sx={{ width: 24 }} data-testid={`weight-value-${criterion}`}>
              {weights[criterion] ?? 0}
            </Typography>
          </Stack>
        )
      })}
    </Paper>
  )
}
