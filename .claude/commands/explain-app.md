---
description: Answer a question about this app from its own documents, always saying what is in the demo and what is only in the full design
argument-hint: "<your question, e.g. explain all the tools and what each is for>"
---

## The question: $ARGUMENTS

**If `$ARGUMENTS` is empty:** don't guess at what was meant. Print a short list of the kinds of
question this command answers — the tools and what each does, how a run flows end to end, why a
design decision was taken, what a term in the report means, what is and isn't built, how to run
it — and ask what they'd like to know. Then stop.

---

You are explaining **Research Opportunity Intelligence** to someone who wants to understand it.
You are not writing code and not changing anything. Explaining well is the whole job.

## 1. What this app is

A researcher gives it two things — a **grant call** (a URL or a PDF) and their own **public
profile page** — and it returns **three ranked research directions** they could pursue under that
call, each backed by evidence the tool actually retrieved.

Backend Python + FastAPI (`backend/roia/`). Frontend React + Vite + TypeScript + MUI
(`frontend/src/`). The model is Google Gemini. It does **not** write a proposal; it helps decide
what to write one about.

**Two versions of this product exist on paper, and telling them apart is the point of this
command:**

| | What it is | Where it is described |
|---|---|---|
| **The demo** | What is actually built and running today. ~2 days of work, 22 work items, all done | `demo-spec.md` + `execution-plan.md` |
| **The full tool** | The larger design it was cut down from. ~15 days. **Not built** | `plan.md` |
| **The original ask** | The requirement both came from, including ideas neither version kept | `requirements_design.md` |

## 2. Read before you answer

Read what the question actually needs — not all of it every time, but never fewer than two
sources, and always at least one that tells you what is *built* rather than what was *planned*.

| File | What it holds | Reach for it when |
|---|---|---|
| `demo-spec.md` | **The contract for what exists.** 16 acceptance criteria (§3), non-goals (§4), architecture (§5), API and data contracts (§6) | Almost always. This is the boundary between demo and full |
| `execution-plan.md` | All 22 work items with a `STATUS` line each, recording what was decided, measured and deliberately left out. Ends with **§The review pass** (13 fixes) and **§Known and not fixed** (12 verified limitations) | Any "why is it like that?", any "does it handle…?", any question about a limitation |
| `e2e-flow.md` | The run from input to report in plain English: every step, every tool call, what each tool is for | Any "how does it work?" or "what happens when…?" |
| `how-to-use.md` | The user guide: setup, commands, what inputs to give, what the output means | Any "how do I…?" |
| `README.md` | The short overview, the three ways to run it, the current status | Orientation |
| `plan.md` | The full ~15-day design and the reasoning behind it | Whenever the question touches something the demo does not do — to say what the full version *would* have done |
| `requirements_design.md` | The original product requirement | For intent behind an output field, or an idea neither version kept |
| `tool-comparison.md` | Plain-English comparison: template vs demo vs full tool | When the asker is non-technical, or asks "why not just use X?" |

**Read the code when the question is about what the app actually does.** Documents drift; the
code does not. `backend/roia/pipeline.py` is the whole run in one readable file — the ten stages
in order. `demo-spec.md` §6 is the contract; `backend/roia/api.py` is what is served.

**Precedence when sources disagree, for "what is true today":**

```
the code  >  demo-spec.md  >  execution-plan.md  >  plan.md  >  requirements_design.md
```

If you find a genuine contradiction, say so in the answer with both file references. A silent
pick between two conflicting documents is the one thing that makes this command untrustworthy.

## 3. The rule you may never skip

> **Every time you describe something the demo does not do, label it.**

Use these markers, inline, wherever they apply:

- **✅ In the demo** — built and running now
- **🔜 Full version only** — designed in `plan.md`, deliberately not built. Say *what* it would
  add and *why it was cut* (usually: it did not fit two days)
- **⚠️ Built but limited** — it exists and has a caveat worth knowing. `execution-plan.md`
  §Known and not fixed is the honest list
- **❌ Not planned** — in neither version

Someone reading your answer must never come away believing a `plan.md` feature is available. That
is the failure mode this command exists to prevent: `plan.md` is longer, more detailed and more
impressive than `demo-spec.md`, so it is the easy thing to quote and the wrong thing to quote.

**Concrete examples of the split, so you recognise the pattern:**

| Topic | Demo | Full version |
|---|---|---|
| `confidence` on a direction | Derived in Python from the `evidence_strength` score alone | Five inputs — evidence margin, gap-verification verdict, quote-verification rate, identity confidence, score-perturbation stability (`plan.md` §7.4) |
| Gap verification | 2 signals: a topic trend and a citing count | 4 signals, with an explicit `undetermined` verdict |
| Competitor / collaborator analysis | Not scored. Shown as *"not assessed"* rather than given a zero | A whole stage; two of the nine criteria depend on it |
| Papers | Abstracts only, stored to 400 characters | Full-text retrieval |
| Author identity | Name-matched in OpenAlex, labelled *unverified* | Cross-checked |

## 4. How to answer

1. **Answer the question first.** One or two sentences that would satisfy the asker if they read
   nothing else. Not a preamble, not a restatement of the question.
2. **Then the substance**, at the depth the question implies. "What is X for?" wants a paragraph.
   "Explain all the tools" wants a table.
3. **Cite where it comes from** — `demo-spec.md` §6.2, `backend/roia/pipeline.py:339`, and so on.
   Clickable file references, so the asker can go and look.
4. **Mark the demo/full split** wherever it applies (§3).
5. **Say what you are unsure of.** If the documents do not answer it and the code does not either,
   say that plainly rather than constructing a plausible answer.

Match the asker's register. A question in plain English gets plain English back — no acceptance
criteria numbers, no module paths, unless they asked in those terms. A question that names a
file gets a technical answer.

**Length is set by the question, not by the amount you read.** Reading five documents to answer
"what does `topic_trend` do?" is correct; replying with five documents' worth of prose is not.

## 5. A worked shape — "explain all tools implemented in this app and their purpose"

The run is a fixed sequence of Python steps, four of which call the model. Read
`backend/roia/pipeline.py` for the sequence and `e2e-flow.md` §9 for the table. The answer should
be the table plus a sentence on the ordering constraint that makes the whole thing work:

**LLM #3 proposes directions with no literature in front of it; LLM #4 writes the gaps with the
literature in front of it.** Reversed, the tool asserts gaps it has no evidence for — which is the
exact bug the spec was rewritten to fix (`demo-spec.md` §5, `execution-plan.md` WI-1.6b/c).

Then per tool: its name, which stage calls it, what it retrieves, what evidence rows it mints, and
whether the model is involved. And a closing note on what is **not** a tool here — ranking and the
report render are plain Python, deliberately.

## 6. Do not

| Don't | Why |
|---|---|
| Describe a `plan.md` feature without marking it 🔜 | The reader will think it is available. This is the main risk |
| Change any file | This command explains. `/fix-in-app` changes |
| Answer from memory of this repo | Read the files. Details have moved, and some of the docs record decisions that were later reversed |
| Pad a short answer to look thorough | A three-line question deserves a three-line answer |
| Quote an acceptance criterion at someone who asked in plain English | Translate it |
| Present a `⚠️ Known and not fixed` item as working | Those are verified limitations; the asker deserves to know |

## 7. Finish

End with **"Want me to go deeper on any of these?"** only if the answer genuinely opened up
sub-topics. Otherwise just stop — a good answer does not need a sign-off.
