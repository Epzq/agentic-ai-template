import Box from '@mui/material/Box'
import Chip from '@mui/material/Chip'
import Divider from '@mui/material/Divider'
import Drawer from '@mui/material/Drawer'
import Link from '@mui/material/Link'
import Stack from '@mui/material/Stack'
import Typography from '@mui/material/Typography'

import type { Evidence } from '../types'

/**
 * One retrieved record, in full.
 *
 * The link is `record.url` and nothing else. **Python minted every URL here** — either it
 * fetched that address or received it inside a fetched API response (AC4) — and no model
 * ever saw a field it could put one in (AC5). A `grant_doc` row legitimately has no URL of
 * its own; it names a page of a document whose sha256 is recorded, so it shows that instead
 * of a dead link.
 */
export function EvidencePanel({
  record,
  onClose,
}: {
  record: Evidence | null
  onClose: () => void
}) {
  return (
    <Drawer anchor="right" open={record !== null} onClose={onClose}>
      <Box sx={{ width: { xs: 320, sm: 420 }, p: 3 }} data-testid="evidence-panel">
        {record && (
          <Stack spacing={2}>
            <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
              <Chip size="small" label={record.id} data-testid="panel-id" />
              <Chip
                size="small"
                variant="outlined"
                label={record.source_type}
                data-testid="panel-source-type"
              />
              {record.year !== null && <Chip size="small" variant="outlined" label={record.year} />}
            </Stack>

            <Typography variant="h6" data-testid="panel-title">
              {record.title}
            </Typography>

            {record.authors.length > 0 && (
              <Typography variant="body2" color="text.secondary" data-testid="panel-authors">
                {record.authors.join(', ')}
              </Typography>
            )}

            {record.summary && (
              <>
                <Divider />
                <Typography variant="body2" data-testid="panel-summary">
                  {record.summary}
                </Typography>
              </>
            )}

            {record.quote && (
              <Box
                component="blockquote"
                data-testid="panel-quote"
                sx={{ m: 0, pl: 2, borderLeft: '3px solid', borderColor: 'divider' }}
              >
                <Typography variant="body2" sx={{ fontStyle: 'italic' }}>
                  “{record.quote}”
                </Typography>
              </Box>
            )}

            <Divider />

            {record.url ? (
              <Link
                href={record.url}
                target="_blank"
                rel="noopener noreferrer"
                data-testid="panel-link"
                sx={{ wordBreak: 'break-all' }}
              >
                {record.url}
              </Link>
            ) : (
              <Typography variant="body2" color="text.secondary" data-testid="panel-no-link">
                {record.page !== null
                  ? `Page ${record.page} of the uploaded call document`
                  : 'No address — this record came from a document, not a page.'}
              </Typography>
            )}

            <Typography variant="caption" color="text.secondary" data-testid="panel-provenance">
              Retrieved {new Date(record.retrieved_at).toISOString().slice(0, 19).replace('T', ' ')}
              {record.http_status !== null && ` · HTTP ${record.http_status}`}
              {record.derived_from !== null && ` · from ${record.derived_from}`}
              {record.sha256 !== null && ` · sha256 ${record.sha256.slice(0, 12)}…`}
            </Typography>
          </Stack>
        )}
      </Box>
    </Drawer>
  )
}
