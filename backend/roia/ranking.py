"""The ranking arithmetic — pure Python, no LLM.

The overall score is a weighted mean the browser can recompute with the identical formula,
which is the only reason the weight sliders can be honest (AC6). A model that produced the
overall directly would make the sliders decorative and the report unreproducible.

``competitive_differentiation`` and ``collaboration_potential`` are ``None`` in the demo
(non-goal §4): excluded from the sum, rendered "not assessed", and the remaining weights
renormalised over the scored seven.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Literal

from roia.llm_schemas import CRITERIA, CriterionScore

#: Flat by default. Grant-derived weights are `plan.md` §7.3 and out of scope here.
#: All nine keys ship to the browser so every slider has something to move, including the
#: two whose criterion is unscored — moving those changes nothing, which is the truth.
DEFAULT_WEIGHTS: dict[str, float] = {name: 1 / len(CRITERIA) for name in CRITERIA}

#: `fixtures/report-sample.json` stores `overall` to 2 dp. Round the same way or a golden
#: test fails on float noise that means nothing.
PLACES = 2
SCALE = 10**PLACES

#: The `evidence_strength` rubric's own anchors, read off `llm.py`'s RUBRICS — **not numbers
#: chosen to taste**:
#:   8 — "several papers' abstracts were retrieved, and a trend and a citing count both
#:       point the same way"
#:   5 — "several retrieved records support the claim, but none were read beyond their titles"
#:   2 — "the claim rests on one retrieved record, or on a query that returned almost nothing"
#: So `high` is the 8-anchor, `medium` the 5-anchor, and everything below is `low`.
CONFIDENCE_HIGH = 8.0
CONFIDENCE_MEDIUM = 5.0

Confidence = Literal["high", "medium", "low"]


def confidence_for(
    scores: Mapping[str, CriterionScore | None], *, thin_evidence: bool = False
) -> Confidence:
    """How much the evidence supports the direction — **derived, never asserted.**

    This used to be a field the model filled in about its own output, which is the one thing
    it is least able to judge and the only place in the report where a claim had nothing
    behind it. Everything else here is checkable: each score cites evidence, the overall is
    arithmetic the browser repeats. Now confidence is too — it is a reading of
    `evidence_strength`, which is itself scored against a rubric and carries its own
    citations.

    On the two recorded runs this reproduces what the model said for all six directions, so
    the change buys a guarantee rather than different answers.

    ``thin_evidence`` caps it at ``low``. That flag means the direction ended up below the
    citation floor after unresolvable ids were dropped, which is a fact about the direction
    the per-criterion score cannot see — a model can score `evidence_strength` 8 on evidence
    that later fails to resolve.
    """
    strength = scores.get("evidence_strength")
    if strength is None or thin_evidence:
        return "low"
    if strength.value >= CONFIDENCE_HIGH:
        return "high"
    if strength.value >= CONFIDENCE_MEDIUM:
        return "medium"
    return "low"


def _round_half_up(value: float) -> float:
    """Round to `PLACES` the way the browser does — bit for bit, not merely similarly.

    `ranking.ts` computes `Math.round(v * 100) / 100`, which is half-**up**. The builtin
    `round()` is half-to-**even**, so the two copies disagreed on every value landing exactly
    on a half: a raw 5.625 was 5.62 here and 5.63 in the browser. Against the real `run-004`
    report that is 1.2% of slider positions — the backend writing one number into
    `report.json` while the slider beside it shows another, which is the drift AC6 exists to
    rule out.

    `math.floor(v * SCALE + 0.5)` is what `Math.round` is *defined* as, evaluated in the same
    order over the same IEEE-754 doubles, so it agrees with the browser on every input rather
    than on most of them. `Decimal.quantize(ROUND_HALF_UP)` would round the true decimal value
    rather than the double and put the two back out of step wherever `v * SCALE` is inexact.

    Nothing already written moves: at the default flat weights all six recorded runs round
    identically either way. This changes only the numbers the sliders produce, and changes
    them to the ones already on screen.
    """
    return math.floor(value * SCALE + 0.5) / SCALE


def compute_ranking(
    scores: Mapping[str, CriterionScore | None],
    weights: Mapping[str, float] = DEFAULT_WEIGHTS,
) -> float:
    """The weighted mean over the criteria that were actually scored.

    Renormalising over the scored subset is what makes flat weights give the plain mean of
    the seven, rather than five-ninths of it. A direction with nothing scored is 0.0, not a
    division by zero.
    """
    #: Accumulated **exactly** as `ranking.ts` accumulates it: sum `weight * value`, then
    #: divide once at the end. Dividing each term by `total` first is algebraically the same
    #: and numerically is not — it diverged from the browser on 0.08% of weight vectors even
    #: after the rounding was fixed, because the two sides were summing different floats
    #: before they ever reached the rounding. Same operations, same order, same doubles.
    total = 0.0
    weighted = 0.0
    for name, score in scores.items():
        weight = weights.get(name, 0.0)
        if score is None or weight <= 0:
            continue
        total += weight
        weighted += weight * score.value
    if total <= 0:
        return 0.0
    return _round_half_up(weighted / total)
