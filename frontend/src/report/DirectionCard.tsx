import Alert from '@mui/material/Alert'
import Box from '@mui/material/Box'
import Card from '@mui/material/Card'
import CardContent from '@mui/material/CardContent'
import Chip from '@mui/material/Chip'
import Divider from '@mui/material/Divider'
import Stack from '@mui/material/Stack'
import Tooltip from '@mui/material/Tooltip'
import Typography from '@mui/material/Typography'

import { CRITERIA, label, NOT_ASSESSED } from '../ranking'
import type { Direction, Evidence } from '../types'
import { EvidenceChips } from './EvidenceChips'
import { Prose } from './Prose'

/**
 * One ranked direction (AC2).
 *
 * `rank` and `overall` come in as props rather than off the record, because the sliders
 * re-rank in the browser (AC6) and the values baked into the report are only the ones the
 * default weights produce.
 */
export function DirectionCard({
  direction,
  rank,
  overall,
  byId,
  onOpen,
}: {
  direction: Direction
  rank: number
  overall: number
  byId: Map<string, Evidence>
  onOpen: (record: Evidence) => void
}) {
  return (
    <Card variant="outlined" data-testid="direction-card" data-rank={rank}>
      <CardContent>
        <Stack
          direction="row"
          spacing={2}
          sx={{ alignItems: 'flex-start', justifyContent: 'space-between', mb: 1 }}
        >
          <Stack direction="row" spacing={1.5} sx={{ alignItems: 'baseline' }}>
            <Typography variant="h5" color="text.secondary" data-testid="direction-rank">
              #{rank}
            </Typography>
            <Typography variant="h6" data-testid="direction-title">
              {direction.title}
            </Typography>
          </Stack>
          <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
            <Chip
              label={overall.toFixed(2)}
              color="primary"
              data-testid="direction-overall"
              title="Weighted mean of the criteria that were scored"
            />
            <Tooltip
              title={
                `Confidence is derived from the evidence-strength score (` +
                `${direction.scores.evidence_strength?.value.toFixed(1) ?? 'not scored'}` +
                `), not asserted by the model.`
              }
            >
              <Chip
                size="small"
                variant="outlined"
                label={`${direction.confidence} confidence`}
                data-testid="direction-confidence"
              />
            </Tooltip>
          </Stack>
        </Stack>

        {direction.thin_evidence && (
          <Alert severity="warning" sx={{ mb: 2 }} data-testid="direction-thin-evidence">
            Thin evidence — this direction resolved fewer citations than the floor asks for.
          </Alert>
        )}

        <Section
          heading="Problem"
          text={direction.problem_statement.text}
          ids={direction.problem_statement.evidence_ids}
          testid="direction-problem"
          byId={byId}
          onOpen={onOpen}
        />

        <Section
          heading="Evidence-backed gap"
          text={direction.evidence_backed_gap.text}
          ids={direction.evidence_backed_gap.evidence_ids}
          testid="direction-gap"
          byId={byId}
          onOpen={onOpen}
        />

        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={3} sx={{ mt: 2 }}>
          <Bullets heading="Strengths" items={direction.key_strengths} testid="direction-strengths" />
          <Bullets
            heading="Weaknesses"
            items={direction.key_weaknesses}
            testid="direction-weaknesses"
          />
        </Stack>

        <Box sx={{ mt: 2 }} data-testid="direction-evidence">
          <Typography variant="overline" color="text.secondary">
            Cited evidence
          </Typography>
          {/* `direction.evidence_ids` is the union across every field — the set AC3 counts
              (">= 2") and AC11 checks for a paper and a grant document. Rendering the union
              itself, rather than leaving it implied by the per-field chips, is what makes
              both criteria answerable by looking at the card. */}
          <EvidenceChips
            ids={direction.evidence_ids}
            byId={byId}
            onOpen={onOpen}
            testid="evidence-chip"
          />
        </Box>

        <Divider sx={{ my: 2 }} />

        <Typography variant="overline" color="text.secondary">
          Scores
        </Typography>
        <Box data-testid="direction-scores">
          {CRITERIA.map((criterion) => {
            const score = direction.scores[criterion] ?? null
            const assessed = !NOT_ASSESSED.includes(criterion)
            return (
              <Box
                key={criterion}
                data-testid="criterion-row"
                data-criterion={criterion}
                sx={{ py: 0.75, borderBottom: '1px solid', borderColor: 'divider' }}
              >
                <Stack direction="row" spacing={1} sx={{ alignItems: 'baseline' }}>
                  <Typography variant="body2" sx={{ minWidth: 210 }}>
                    {label(criterion)}
                  </Typography>
                  {score === null ? (
                    <Typography
                      variant="body2"
                      color="text.disabled"
                      data-testid="criterion-not-assessed"
                    >
                      not assessed{assessed ? '' : ' — out of scope for this build'}
                    </Typography>
                  ) : (
                    <>
                      <Typography variant="body2" sx={{ fontWeight: 600 }} data-testid="criterion-value">
                        {score.value.toFixed(1)}
                      </Typography>
                      <Typography variant="caption" color="text.secondary">
                        {score.rationale}
                      </Typography>
                    </>
                  )}
                </Stack>
                {score && (
                  <EvidenceChips
                    ids={score.evidence_ids}
                    byId={byId}
                    onOpen={onOpen}
                    testid="criterion-chip"
                  />
                )}
              </Box>
            )
          })}
        </Box>
      </CardContent>
    </Card>
  )
}

function Section({
  heading,
  text,
  ids,
  testid,
  byId,
  onOpen,
}: {
  heading: string
  text: string
  ids: readonly string[]
  testid: string
  byId: Map<string, Evidence>
  onOpen: (record: Evidence) => void
}) {
  return (
    <Box sx={{ mt: 2 }} data-testid={testid}>
      <Typography variant="overline" color="text.secondary">
        {heading}
      </Typography>
      <Prose>{text}</Prose>
      <EvidenceChips ids={ids} byId={byId} onOpen={onOpen} />
    </Box>
  )
}

function Bullets({
  heading,
  items,
  testid,
}: {
  heading: string
  items: readonly string[]
  testid: string
}) {
  if (items.length === 0) return null
  return (
    <Box sx={{ flex: 1 }} data-testid={testid}>
      <Typography variant="overline" color="text.secondary">
        {heading}
      </Typography>
      <Box component="ul" sx={{ m: 0, pl: 2.5 }}>
        {items.map((item, index) => (
          <Typography component="li" variant="body2" key={index}>
            {item}
          </Typography>
        ))}
      </Box>
    </Box>
  )
}
