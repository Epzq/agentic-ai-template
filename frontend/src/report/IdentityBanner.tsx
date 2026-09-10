import Alert from '@mui/material/Alert'

import type { ReportIdentity } from '../types'

/**
 * "Analysing X at Y — unverified".
 *
 * The word **unverified** is not hedging, it is the spec: author disambiguation is a
 * non-goal (§4), so the run resolves a name to the highest-`works_count` OpenAlex author and
 * says out loud that it did not check. `demo-spec.md` §8.5 makes stating this part of the
 * demo protocol — claiming otherwise invites the one question that cannot be answered.
 */
export function IdentityBanner({ identity }: { identity: ReportIdentity | null }) {
  if (!identity) return null
  return (
    <Alert severity="info" data-testid="identity-banner">
      Analysing <strong>{identity.display_name}</strong>
      {identity.institution && (
        <>
          {' '}
          at <strong>{identity.institution}</strong>
        </>
      )}{' '}
      — <strong data-testid="identity-confidence">{identity.confidence}</strong>. The author was
      matched by name in OpenAlex and not otherwise checked.
    </Alert>
  )
}
