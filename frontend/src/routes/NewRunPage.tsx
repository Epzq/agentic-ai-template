import Alert from '@mui/material/Alert'
import AlertTitle from '@mui/material/AlertTitle'
import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import Chip from '@mui/material/Chip'
import CircularProgress from '@mui/material/CircularProgress'
import Divider from '@mui/material/Divider'
import FormControl from '@mui/material/FormControl'
import FormControlLabel from '@mui/material/FormControlLabel'
import FormLabel from '@mui/material/FormLabel'
import Paper from '@mui/material/Paper'
import Radio from '@mui/material/Radio'
import RadioGroup from '@mui/material/RadioGroup'
import Stack from '@mui/material/Stack'
import TextField from '@mui/material/TextField'
import Typography from '@mui/material/Typography'
import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router'

import type { RunSources } from '../api'
import { ApiError, probe, startRun, uploadGrant } from '../api'
import type { ProbeQuestion, ProbeResult } from '../types'

/**
 * Two option values mean **do not start the run** — they are requests to change the input,
 * not answers about it (WI-1.4b). Everything else, including every skipped question, starts
 * the run.
 */
const SEND_ME_BACK: Record<string, string> = {
  use_different_url: 'Paste a profile URL with more on it, then analyse again.',
  upload_document: 'Upload the call document as a PDF, then analyse again.',
}

type Step = 'form' | 'probing' | 'clarify' | 'starting'

export default function NewRunPage() {
  const navigate = useNavigate()
  const fileInput = useRef<HTMLInputElement>(null)

  const [grantUrl, setGrantUrl] = useState('')
  const [profileUrl, setProfileUrl] = useState('')
  const [upload, setUpload] = useState<{ id: string; name: string } | null>(null)
  const [step, setStep] = useState<Step>('form')
  const [result, setResult] = useState<ProbeResult | null>(null)
  //: Which inputs the probe in hand was actually run against. See `stale` below.
  const [probedFor, setProbedFor] = useState('')
  const [answers, setAnswers] = useState<Record<string, string>>({})
  //: Which questions the applicant actually touched. See `chosenOnly` below — this is the
  //: difference between "they picked this" and "they left it alone", and the backend cares.
  const [touched, setTouched] = useState<Set<string>>(new Set())
  const [error, setError] = useState<string | null>(null)
  const [blocked, setBlocked] = useState<string | null>(null)

  const busy = step === 'probing' || step === 'starting'
  const sources: RunSources = {
    profile_url: profileUrl.trim(),
    ...(upload ? { grant_upload_id: upload.id } : { grant_url: grantUrl.trim() }),
  }
  const sourcesKey = JSON.stringify(sources)

  /**
   * The inputs were edited after the probe ran, so the questions on screen came from a page
   * we are no longer talking about.
   *
   * This matters far more than it looks. Sending the new URLs with the old `probe_id` makes
   * the run **reuse the old probe's documents and evidence store** while recording the new
   * URLs as its inputs — a report that names one call and cites evidence from another. On a
   * product whose whole claim is that its citations are real, that is the worst bug
   * available. Derived during render rather than reset in an effect, so there is no window
   * where a stale probe is still live.
   */
  const stale = result !== null && probedFor !== sourcesKey
  const canAnalyse = Boolean((upload || grantUrl.trim()) && profileUrl.trim()) && !busy

  //: One submission at a time. `disabled` only takes effect on the next render, so a fast
  //: double-click on Start fires `onStart` twice and bills two five-minute runs.
  const inFlight = useRef(false)

  function fail(cause: unknown) {
    setError(cause instanceof ApiError ? cause.message : String(cause))
  }

  function backToForm() {
    setStep('form')
    setResult(null)
    setProbedFor('')
    setAnswers({})
    setTouched(new Set())
  }

  /**
   * Only the questions the applicant actually answered.
   *
   * The checklist requires the default to be **pre-selected**, so an untouched radio group
   * still shows a value. Sending that value back would be a lie: `resolve_answers` marks an
   * answer `answered=True` when the posted value matches, and `answers_brief` then drops the
   * "(not answered; default applied)" qualifier — so LLM #1 is told the applicant *chose*
   * "analyse the whole programme" when they simply never touched it. Omitting untouched
   * questions lets the server apply its own default and record it honestly.
   *
   * A consequence worth knowing: pressing "Start run" without touching anything now posts
   * exactly what "Skip" posts, because they are in fact the same act.
   */
  function chosenOnly(): Record<string, string> {
    return Object.fromEntries(
      Object.entries(answers).filter(([code]) => touched.has(code)),
    )
  }

  async function onAnalyse() {
    if (inFlight.current) return
    inFlight.current = true
    setError(null)
    setBlocked(null)
    setStep('probing')
    try {
      const probed = await probe(sources)
      // Pre-select each question's default, so pressing Start without touching anything
      // sends exactly what skipping would (AC14).
      const preselected: Record<string, string> = {}
      for (const question of probed.questions) preselected[question.code] = question.default
      setAnswers(preselected)
      setTouched(new Set())
      setResult(probed)
      setProbedFor(sourcesKey)
      setStep('clarify')
    } catch (cause) {
      fail(cause)
      setStep('form')
    } finally {
      inFlight.current = false
    }
  }

  async function onStart(withAnswers: Record<string, string>) {
    if (inFlight.current) return
    if (stale) {
      // Belt and braces: the panel is already hidden when the probe is stale, so this
      // should be unreachable. It costs one line and the failure it guards is silent.
      setError('The inputs changed since Analyse. Analyse again before starting a run.')
      return
    }
    inFlight.current = true
    setError(null)
    const stopper = Object.values(withAnswers).find((value) => value in SEND_ME_BACK)
    if (stopper) {
      // Not an error: the applicant asked to fix the input, so nothing should start.
      setBlocked(SEND_ME_BACK[stopper])
      backToForm()
      inFlight.current = false
      return
    }
    setStep('starting')
    try {
      const created = await startRun(sources, {
        probe_id: result?.probe_id,
        answers: withAnswers,
      })
      navigate(`/runs/${created.run_id}`)
    } catch (cause) {
      // A 404 here means the server no longer holds the probe these answers were made
      // against — it restarted, most likely. It now refuses rather than running against the
      // wrong call period, so the honest move is to send the applicant back to Analyse.
      if (cause instanceof ApiError && cause.status === 404) {
        backToForm()
        setError(`${cause.message} Press Analyse to read the call again.`)
      } else {
        fail(cause)
        setStep('clarify')
      }
      inFlight.current = false
    }
    // Deliberately not cleared on success: navigation unmounts this page, and re-enabling
    // the button first would open the double-submit window again.
  }

  async function onFile(file: File | undefined) {
    // Clear the input's value whatever happens. A file input keeps its previous value, so
    // after removing the chip and choosing *the same PDF again* no `change` event fires and
    // the click does nothing at all.
    if (fileInput.current) fileInput.current.value = ''
    if (!file) return
    setError(null)
    try {
      const created = await uploadGrant(file)
      setUpload({ id: created.upload_id, name: file.name })
      setGrantUrl('')
    } catch (cause) {
      fail(cause)
    }
  }

  // A file dropped anywhere but the zone makes the browser navigate to it, throwing away a
  // half-filled form — or, mid-demo, the whole app. The zone's own handler runs first, in
  // the target phase, so it still receives the file.
  useEffect(() => {
    const swallow = (event: DragEvent) => event.preventDefault()
    window.addEventListener('dragover', swallow)
    window.addEventListener('drop', swallow)
    return () => {
      window.removeEventListener('dragover', swallow)
      window.removeEventListener('drop', swallow)
    }
  }, [])

  return (
    <Stack spacing={3}>
      <Box>
        <Typography variant="h4" gutterBottom>
          Analyse a grant call
        </Typography>
        <Typography color="text.secondary">
          Give it the call and your public profile. It returns three ranked directions, each
          backed by evidence it actually retrieved.
        </Typography>
      </Box>

      {error && (
        <Alert severity="error" data-testid="form-error" onClose={() => setError(null)}>
          {error}
        </Alert>
      )}
      {blocked && (
        <Alert severity="info" data-testid="blocked-alert" onClose={() => setBlocked(null)}>
          <AlertTitle>Nothing started</AlertTitle>
          {blocked}
        </Alert>
      )}

      <Paper variant="outlined" sx={{ p: 3 }}>
        <Stack spacing={2}>
          <TextField
            label="Grant call URL"
            placeholder="https://www.rgp.gov.sg/nrf-ar/crp"
            value={grantUrl}
            disabled={Boolean(upload) || busy}
            onChange={(event) => setGrantUrl(event.target.value)}
            slotProps={{ htmlInput: { 'data-testid': 'grant-url-input' } }}
            fullWidth
          />

          <Divider>or</Divider>

          <Box
            data-testid="grant-drop-zone"
            onDragOver={(event) => event.preventDefault()}
            onDrop={(event) => {
              event.preventDefault()
              void onFile(event.dataTransfer.files[0])
            }}
            onClick={() => fileInput.current?.click()}
            sx={{
              p: 2,
              border: '1px dashed',
              borderColor: 'divider',
              borderRadius: 1,
              textAlign: 'center',
              cursor: 'pointer',
            }}
          >
            <input
              ref={fileInput}
              type="file"
              accept="application/pdf"
              hidden
              data-testid="grant-file-input"
              onChange={(event) => void onFile(event.target.files?.[0])}
            />
            {upload ? (
              <Stack
                direction="row"
                spacing={1}
                sx={{ justifyContent: 'center', alignItems: 'center' }}
              >
                <Chip label={upload.name} data-testid="grant-upload-chip" />
                <Button
                  size="small"
                  data-testid="grant-upload-remove"
                  // Without this the click bubbles to the drop zone's own onClick and
                  // immediately re-opens the file picker you were trying to get out of.
                  onClick={(event) => {
                    event.stopPropagation()
                    setUpload(null)
                  }}
                >
                  Remove
                </Button>
              </Stack>
            ) : (
              <Typography variant="body2" color="text.secondary">
                Drop the call PDF here, or click to choose one (≤25 MB)
              </Typography>
            )}
          </Box>

          <TextField
            label="Researcher profile URL"
            placeholder="https://example.edu/~you"
            value={profileUrl}
            disabled={busy}
            onChange={(event) => setProfileUrl(event.target.value)}
            slotProps={{ htmlInput: { 'data-testid': 'profile-url-input' } }}
            fullWidth
          />

          <Box>
            <Button
              variant="contained"
              size="large"
              disabled={!canAnalyse}
              onClick={() => void onAnalyse()}
              data-testid="analyse-button"
              startIcon={step === 'probing' ? <CircularProgress size={16} /> : undefined}
            >
              {step === 'probing' ? 'Analysing…' : 'Analyse'}
            </Button>
            <Typography variant="caption" color="text.secondary" sx={{ ml: 2 }}>
              {/* ~10s was the estimate in demo-spec §"Pre-flight clarification"; the
                  measurement that replaced it is 17.5s on the demo pair (19.3s cold), against
                  AC14's 20s budget. Promising 10 and taking 18 is a small lie, and this is the
                  one product where the copy should not be doing that. */}
              About 20 seconds. Reads the pages; asks no model anything.
            </Typography>
          </Box>
        </Stack>
      </Paper>

      {stale && (
        <Alert severity="info" data-testid="stale-probe">
          The inputs changed since you pressed Analyse. Analyse again — the questions below
          came from the previous page.
        </Alert>
      )}

      {step !== 'form' && result && !stale && (
        <Clarify
          result={result}
          answers={answers}
          // `busy`, not just `starting`: while a re-probe is in flight the guard in
          // `onStart` refuses anyway, so a live-looking Start would be a dead button.
          busy={busy}
          onAnswer={(code, value) => {
            setAnswers((prior) => ({ ...prior, [code]: value }))
            setTouched((prior) => new Set(prior).add(code))
          }}
          onStart={() => void onStart(chosenOnly())}
          onSkip={() => void onStart({})}
        />
      )}
    </Stack>
  )
}

function Clarify(props: {
  result: ProbeResult
  answers: Record<string, string>
  busy: boolean
  onAnswer: (code: string, value: string) => void
  onStart: () => void
  onSkip: () => void
}) {
  const { result, answers, busy, onAnswer, onStart, onSkip } = props
  const [dismissed, setDismissed] = useState<ReadonlySet<number>>(new Set())
  const onDismiss = (index: number) => setDismissed((prior) => new Set(prior).add(index))
  return (
    <Paper variant="outlined" sx={{ p: 3 }} data-testid="clarify-panel">
      <Typography variant="h6" gutterBottom>
        Before the run starts
      </Typography>

      {result.warnings.map((warning, index) =>
        dismissed.has(index) ? null : (
          // Keyed by index: `code` is not unique — two failed fetches both arrive as
          // `fetch_failed`, and React would render only the first.
          <Alert
            key={index}
            severity="warning"
            sx={{ mb: 2 }}
            data-testid="probe-warning"
            onClose={() => onDismiss(index)}
          >
            {warning.message}
          </Alert>
        ),
      )}

      {result.questions.length === 0 ? (
        <Typography color="text.secondary" data-testid="no-questions" sx={{ mb: 2 }}>
          Nothing ambiguous — the call and the profile both read cleanly.
        </Typography>
      ) : (
        <Stack spacing={3} sx={{ mb: 3 }}>
          {result.questions.map((question) => (
            <Question
              key={question.code}
              question={question}
              value={answers[question.code] ?? question.default}
              onChange={(value) => onAnswer(question.code, value)}
            />
          ))}
        </Stack>
      )}

      <Stack direction="row" spacing={2} sx={{ alignItems: 'center' }}>
        <Button
          variant="contained"
          size="large"
          disabled={busy}
          onClick={onStart}
          data-testid="start-run-button"
          startIcon={busy ? <CircularProgress size={16} /> : undefined}
        >
          {busy ? 'Starting…' : 'Start run'}
        </Button>
        {result.questions.length > 0 && (
          <Button disabled={busy} onClick={onSkip} data-testid="skip-questions-button">
            Skip and use the defaults
          </Button>
        )}
      </Stack>
    </Paper>
  )
}

function Question(props: {
  question: ProbeQuestion
  value: string
  onChange: (value: string) => void
}) {
  const { question, value, onChange } = props
  return (
    <FormControl data-testid={`probe-question-${question.code}`}>
      <FormLabel sx={{ mb: 1 }}>{question.question}</FormLabel>
      <RadioGroup value={value} onChange={(event) => onChange(event.target.value)}>
        {question.options.map((option) => (
          <FormControlLabel
            key={option.value}
            value={option.value}
            label={
              option.value === question.default ? `${option.label} (default)` : option.label
            }
            control={
              <Radio
                size="small"
                slotProps={{
                  input: {
                    'data-testid': `probe-option-${question.code}-${option.value}`,
                  } as React.InputHTMLAttributes<HTMLInputElement>,
                }}
              />
            }
          />
        ))}
      </RadioGroup>
    </FormControl>
  )
}
