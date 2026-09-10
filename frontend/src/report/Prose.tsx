import Box from '@mui/material/Box'
import rehypeSanitize, { defaultSchema } from 'rehype-sanitize'
import remarkGfm from 'remark-gfm'
import Markdown from 'react-markdown'

/**
 * Model-authored prose, rendered as markdown.
 *
 * **`rehype-raw` is deliberately absent.** It would let raw HTML through, and this text
 * comes from a language model that was handed the contents of fetched web pages and PDFs —
 * exactly the path by which page content becomes markup in the report. `rehype-sanitize`
 * with the default schema strips anything that is not plain formatting.
 *
 * **`a` is stripped as well**, which the default schema does *not* do: it allows `a` with
 * `http`/`https` hrefs, and `remark-gfm` turns a bare `https://…` into one. Between them, a
 * URL the model invented inside `problem_statement.text` rendered as a live citation
 * directly above the real evidence chips. `llm_schemas.strip_urls` now removes those
 * server-side, and this is the second lock: only `EvidenceChips` may produce a link in a
 * report, because only it is rendering something Python actually fetched (AC13).
 */
const NO_ANCHORS = {
  ...defaultSchema,
  tagNames: (defaultSchema.tagNames ?? []).filter((tag) => tag !== 'a'),
}
export function Prose({ children, testid }: { children: string; testid?: string }) {
  return (
    <Box
      data-testid={testid}
      sx={{
        '& p': { my: 0.5 },
        '& p:first-of-type': { mt: 0 },
        '& p:last-of-type': { mb: 0 },
        // No `& a` rule: anchors cannot occur here — see NO_ANCHORS above.
        '& code': { fontSize: '0.85em', bgcolor: 'action.hover', px: 0.5, borderRadius: 0.5 },
      }}
    >
      <Markdown remarkPlugins={[remarkGfm]} rehypePlugins={[[rehypeSanitize, NO_ANCHORS]]}>
        {children}
      </Markdown>
    </Box>
  )
}
