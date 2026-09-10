/**
 * The ranking arithmetic, mirrored from `backend/roia/ranking.py`.
 *
 * This is the one piece of logic that deliberately exists twice, and it has to agree to the
 * last decimal: AC6 says a slider re-orders the directions **with zero network requests**,
 * so the browser recomputes rather than asks. A test asserts that at the default weights
 * this reproduces the `overall` the backend already wrote into the report — if the two ever
 * drift, that fails rather than the sliders quietly lying.
 *
 * Rule 2 of the project still holds: **no model is involved in either copy.**
 */

import type { CriterionScore } from './types'

/** `llm_schemas.CRITERIA`, in §6.4 order. The matrix and the sliders both render in this order. */
export const CRITERIA = [
  'grant_alignment',
  'scientific_novelty',
  'importance',
  'applicant_fit',
  'feasibility',
  'competitive_differentiation',
  'collaboration_potential',
  'impact_potential',
  'evidence_strength',
] as const

export type Criterion = (typeof CRITERIA)[number]

/**
 * Scored `null` in the demo — the competitor and collaborator stage is a non-goal (§4).
 * They still get a slider, because moving it changing nothing is the honest thing to show.
 */
export const NOT_ASSESSED: readonly Criterion[] = [
  'competitive_differentiation',
  'collaboration_potential',
]

/** Sliders are integers so the URL stays exact — no float noise round-tripping through it. */
export const WEIGHT_MIN = 0
export const WEIGHT_MAX = 10
export const WEIGHT_DEFAULT = 5

export type Weights = Record<string, number>

export const DEFAULT_WEIGHTS: Weights = Object.fromEntries(
  CRITERIA.map((name) => [name, WEIGHT_DEFAULT]),
)

export function label(criterion: string): string {
  return criterion.replace(/_/g, ' ').replace(/^./, (c) => c.toUpperCase())
}

/**
 * The weighted mean over the criteria that were actually scored — `compute_ranking()` in
 * `ranking.py`, line for line.
 *
 * Renormalising over the scored subset is what makes equal weights give the plain mean of
 * the seven rather than five-ninths of it, and it is why integer sliders reproduce the
 * backend's flat `1/9` weights exactly: 5/35 and (1/9)/(7/9) are both 1/7.
 */
export function computeOverall(
  scores: Record<string, CriterionScore | null>,
  weights: Weights = DEFAULT_WEIGHTS,
): number {
  let total = 0
  let weighted = 0
  for (const [name, score] of Object.entries(scores)) {
    const weight = weights[name] ?? 0
    if (score === null || weight <= 0) continue
    total += weight
    weighted += weight * score.value
  }
  if (total <= 0) return 0
  // `compute_ranking` in ranking.py performs these same operations in this same order, on
  // purpose. Two things had to be fixed to make that true, and both are easy to undo:
  //   1. it rounded with Python's builtin `round()` (half-to-even), so a raw 5.625 became
  //      5.62 there and 5.63 here;
  //   2. it divided each term by `total` before summing instead of dividing once at the end,
  //      which is algebraically the same and numerically is not — that alone left 0.08% of
  //      weight vectors disagreeing after the rounding was fixed.
  // So: do not "simplify" the accumulation below, and if you change the rounding, change it
  // there in the same commit. A sweep test in test_report.py fails if these drift apart.
  return Math.round((weighted / total) * 100) / 100
}

export interface Ranked<T> {
  item: T
  overall: number
  rank: number
}

/**
 * Re-rank by the recomputed overall. Ties keep their original order, so a slider that
 * changes nothing does not shuffle the cards.
 */
export function rankBy<T extends { scores: Record<string, CriterionScore | null> }>(
  items: readonly T[],
  weights: Weights,
): Ranked<T>[] {
  return items
    .map((item, index) => ({ item, overall: computeOverall(item.scores, weights), index }))
    .sort((a, b) => b.overall - a.overall || a.index - b.index)
    .map((entry, position) => ({ item: entry.item, overall: entry.overall, rank: position + 1 }))
}

// --- weights in the URL ---------------------------------------------------------------------

/**
 * Nine integers in `CRITERIA` order, e.g. `?w=5,5,9,5,5,5,5,5,5`. Positional rather than
 * named so the URL stays short enough to paste into a chat window, which is the whole point
 * of putting the weights there: "look at it with novelty turned up" is one link.
 */
export function encodeWeights(weights: Weights): string {
  return CRITERIA.map((name) => weights[name] ?? WEIGHT_DEFAULT).join(',')
}

export function decodeWeights(encoded: string | null): Weights {
  if (!encoded) return DEFAULT_WEIGHTS
  const parts = encoded.split(',')
  if (parts.length !== CRITERIA.length) return DEFAULT_WEIGHTS
  const weights: Weights = {}
  for (const [index, name] of CRITERIA.entries()) {
    const value = Number(parts[index])
    // A hand-edited URL must not be able to produce NaN weights and a blank report.
    weights[name] = Number.isFinite(value)
      ? Math.min(WEIGHT_MAX, Math.max(WEIGHT_MIN, Math.round(value)))
      : WEIGHT_DEFAULT
  }
  return weights
}

export function isDefault(weights: Weights): boolean {
  return CRITERIA.every((name) => (weights[name] ?? WEIGHT_DEFAULT) === WEIGHT_DEFAULT)
}
