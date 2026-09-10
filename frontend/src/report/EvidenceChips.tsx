import Chip from '@mui/material/Chip'
import Stack from '@mui/material/Stack'
import Tooltip from '@mui/material/Tooltip'

import type { Evidence } from '../types'

/** A shade per provenance, so "which of these is a paper?" is answerable at a glance (AC11). */
const TONE: Record<string, 'primary' | 'secondary' | 'default' | 'info'> = {
  paper: 'primary',
  grant_doc: 'secondary',
  api_query: 'info',
  webpage: 'default',
}

/**
 * The evidence behind one field, resolved from ID to record.
 *
 * An ID that does not resolve is **rendered as broken rather than hidden**. The backend
 * already drops unresolvable IDs with a `unresolvable_evidence_id` warning (AC10a), so one
 * arriving here means something is wrong upstream — and silently omitting it would turn
 * AC3's "every ID resolves to a stored record" into a claim nobody could check.
 */
export function EvidenceChips({
  ids,
  byId,
  onOpen,
  testid = 'evidence-chip',
}: {
  ids: readonly string[]
  byId: Map<string, Evidence>
  onOpen: (record: Evidence) => void
  testid?: string
}) {
  if (ids.length === 0) return null
  return (
    <Stack direction="row" spacing={0.5} sx={{ flexWrap: 'wrap', gap: 0.5, mt: 0.75 }}>
      {ids.map((id) => {
        const record = byId.get(id)
        if (!record) {
          return (
            <Chip
              key={id}
              size="small"
              color="error"
              variant="outlined"
              label={`${id} — missing`}
              data-testid="evidence-chip-missing"
            />
          )
        }
        return (
          <Tooltip key={id} title={record.title} enterDelay={200}>
            <Chip
              size="small"
              color={TONE[record.source_type] ?? 'default'}
              variant="outlined"
              label={id}
              onClick={() => onOpen(record)}
              data-testid={testid}
              data-source-type={record.source_type}
            />
          </Tooltip>
        )
      })}
    </Stack>
  )
}
