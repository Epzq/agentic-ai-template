import Alert from '@mui/material/Alert'
import AlertTitle from '@mui/material/AlertTitle'
import Button from '@mui/material/Button'
import Stack from '@mui/material/Stack'
import { useState } from 'react'

import type { RunEvent } from './types'

/**
 * The run's warnings, dismissible (AC9).
 *
 * **Dismissed, never deleted.** A warning is the honest half of the report — "the profile
 * page yielded 412 characters", "only 3 papers came back" — and a run that hides them once
 * clicked would be claiming more than it retrieved. Dismissal is per-browser view only, the
 * events are untouched, and a "show N dismissed" button brings them back.
 *
 * Keyed by `seq` rather than by `code`: two failed fetches both arrive as `fetch_failed`,
 * and dismissing one must not dismiss the other.
 */
const HUMAN: Record<string, string> = {
  thin_profile: 'The profile page had very little on it',
  thin_literature: 'A direction returned few papers',
  thin_extraction: 'A page yielded almost no text',
  fetch_failed: 'Something could not be fetched',
  quote_unverified: 'A quote could not be matched to its source verbatim',
  compressed_scores: 'The scores are close together, so the weight sliders move little',
  unresolvable_evidence_id: 'A citation was dropped because it named no stored record',
  robots_disallowed: 'A page was skipped because robots.txt disallows it',
  stage_failed: 'A stage failed and the run carried on without it',
  // The nine above were the ones the demo run happens to produce. These are the rest —
  // every code the backend can emit now has a sentence, because a run that goes wrong is
  // exactly when the user is reading this box, and `llm_failed` told them nothing.
  // `test_every_backend_warning_code_has_a_human_label` fails if a new one is added
  // without a label.
  author_unresolved: 'The researcher could not be matched in the publication database',
  identity_inputs_missing: 'No researcher name could be read from the profile page',
  openalex_failed: 'A publication-database lookup did not return data',
  llm_failed: 'An AI call did not come back, so that step was skipped',
  llm_invalid_output: 'An AI call returned something unusable, so that step was skipped',
  no_candidates: 'No research directions could be proposed',
  no_assessment: 'The directions could not be scored',
  thin_evidence: 'A direction has less evidence behind it than the report requires',
  evidence_rejected: 'A retrieved record could not be stored',
  unsupported_type: 'A linked file was in a format this tool does not read',
  model_wrote_a_url: 'The model wrote a web address into its prose; it was removed',
}

export function Warnings({ events }: { events: readonly RunEvent[] }) {
  const [dismissed, setDismissed] = useState<ReadonlySet<number>>(new Set())

  const warnings = events.filter((event) => event.type === 'warning')
  const showing = warnings.filter((warning) => !dismissed.has(warning.seq))
  const hidden = warnings.length - showing.length

  if (warnings.length === 0) return null

  return (
    <Stack spacing={1} data-testid="warnings">
      {showing.map((warning) => {
        const code = String(warning.code ?? 'warning')
        return (
          <Alert
            key={warning.seq}
            severity="warning"
            data-testid="run-warning"
            data-code={code}
            onClose={() => setDismissed((prior) => new Set(prior).add(warning.seq))}
            slotProps={{
              closeButton: {
                'data-testid': 'dismiss-warning',
              } as React.ButtonHTMLAttributes<HTMLButtonElement>,
            }}
          >
            <AlertTitle sx={{ mb: 0 }}>{HUMAN[code] ?? code}</AlertTitle>
            {String(warning.message ?? '')}
          </Alert>
        )
      })}

      {hidden > 0 && (
        <Button
          size="small"
          onClick={() => setDismissed(new Set())}
          data-testid="restore-warnings"
          sx={{ alignSelf: 'flex-start' }}
        >
          Show {hidden} dismissed warning{hidden === 1 ? '' : 's'}
        </Button>
      )}
    </Stack>
  )
}
