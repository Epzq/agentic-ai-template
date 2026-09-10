/**
 * The wire contract, mirrored from the Pydantic models in `backend/roia/`.
 *
 * These are hand-written rather than generated because the demo has four endpoints and a
 * codegen step is one more thing to break on the morning. The rule that keeps them honest:
 * **every field here exists in a Python model** — `api.py` for the envelopes, `ingest.py`
 * for the probe, `report.py` and `evidence.py` for the report.
 */

/** `evidence.py` — the four provenance rules AC4 enforces are keyed off this. */
export type SourceType = 'grant_doc' | 'webpage' | 'paper' | 'api_query'

/** `api.py: RunStatus`. `report` is non-null only once this is `finished`. */
export type RunStatus = 'running' | 'finished' | 'failed'

export interface IngestWarning {
  code: string
  message: string
}

/**
 * `events.py: Event` — `{seq, ts, type, …}` with the payload flattened to the top level
 * (the model is `extra="allow"`), so the payload fields vary by `type`.
 */
export interface RunEvent {
  seq: number
  ts: string
  type: string
  [field: string]: unknown
}

// --- the pre-flight probe (WI-1.4b) ------------------------------------------------------

export interface ProbeOption {
  value: string
  label: string
  /** The evidence rows this option was found on. Resolvable once the run has a store. */
  evidence_ids: string[]
}

export interface ProbeQuestion {
  code: string
  question: string
  options: ProbeOption[]
  /** Applied when the applicant skips. Skipping is always allowed (AC14). */
  default: string
}

export interface ProbeResult {
  probe_id: string
  detected: Record<string, unknown>
  questions: ProbeQuestion[]
  warnings: IngestWarning[]
}

// --- the report (rendered by WI-2.5; typed here because the snapshot carries it) ----------

export interface Evidence {
  id: string
  source_type: SourceType
  url: string | null
  title: string
  authors: string[]
  year: number | null
  page: number | null
  sha256: string | null
  quote: string | null
  summary: string
  derived_from: string | null
  http_status: number | null
  retrieved_at: string
}

export interface CriterionScore {
  evidence_ids: string[]
  value: number
  rationale: string
  provenance: 'computed' | 'judged'
}

export interface DirectionSection {
  evidence_ids: string[]
  text: string
}

export interface Direction {
  rank: number
  overall: number
  confidence: string
  thin_evidence: boolean
  title: string
  problem_statement: DirectionSection
  evidence_backed_gap: DirectionSection
  key_strengths: string[]
  key_weaknesses: string[]
  evidence_ids: string[]
  /** All nine criteria; the two non-goals in §6.4 are `null` — "not assessed". */
  scores: Record<string, CriterionScore | null>
}

export interface ReportInputs {
  grant_url: string
  profile_url: string
  grant_document: string | null
  grant_sha256: string | null
}

export interface ReportIdentity {
  author_id: string
  display_name: string
  institution: string | null
  /** Always `unverified`: disambiguation is a non-goal (§4) and the banner must say so. */
  confidence: string
  margin: number
}

export interface Report {
  run_id: string
  generated_at: string
  inputs: ReportInputs
  identity: ReportIdentity | null
  weights: Record<string, number>
  directions: Direction[]
  evidence: Evidence[]
}

// --- run envelopes ------------------------------------------------------------------------

export interface RunInputs {
  grant_src: string
  profile_url: string
  answers: Record<string, string>
}

export interface RunSnapshot {
  run_id: string
  status: RunStatus
  inputs: RunInputs
  warnings: RunEvent[]
  events: RunEvent[]
  report: Report | null
}

export interface RunCreated {
  run_id: string
}

export interface UploadCreated {
  upload_id: string
  sha256: string
}
