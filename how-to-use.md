# How to use this app

A short, practical guide. No technical background needed.

---

## What it does

You give it **a grant call** and **a researcher's web page**. It gives you back **three
research directions** that researcher could realistically propose to that funder — ranked,
with strengths, weaknesses, and a link behind every claim.

It does **not** write your proposal. It helps you decide what to write one about.

A run takes about **two minutes**.

---

## Part 1 — Setting it up (once)

> ### Already done on this machine
>
> Set-up is **complete** here — you can skip to Part 2. For reference, this is what was
> installed and what to type:
>
> | | |
> |---|---|
> | `PYTHON` | `/home/chinthani/anaconda3/envs/roia/bin/python` |
> | Backend | conda env `roia` (Python 3.12.14), installed via Option B |
> | Frontend | already built — `frontend/dist/` exists, so **Node is not needed** |
> | Keys | already filled in `backend/.env` |
> | Tests | 310 passed |
>
> Option A (`venv`) does **not** work on this machine — the system is missing
> `python3.12-venv`. Option B is why the conda route exists below.
>
> Start the app:
>
> ```bash
> cd backend
> /home/chinthani/anaconda3/envs/roia/bin/python -m uvicorn roia.api:app_factory --factory --port 8000
> ```
>
> Then open <http://localhost:8000>.


### What you need

| | |
|---|---|
| **Python 3.12** | Check with `python3.12 --version` |
| **Node 22** | *Only if you need to rebuild the web page* — see step 3. Check with `node --version`. If you use `nvm`, the right version is already recorded in the project |
| **A Google Gemini key** | From <https://aistudio.google.com/apikey> — **must be a paid-tier key** |
| **An OpenAlex key** | From <https://openalex.org/settings/api> — free, takes about 30 seconds |

> **Why a paid Gemini key?** The final scoring step uses Google's most capable model, which has
> no free tier. The other three steps use the cheap fast model.
>
> **Why an OpenAlex key even though it's free?** Without one you get about 100 database lookups
> *per day*, and a single run uses more than that.

### Set-up steps

Open a terminal in the project folder and run these, one block at a time.

**1. Install the backend**

There are two ways. Pick **one** and use it consistently — whichever you pick decides what
`PYTHON` means in every later command on this page.

*Option A — `venv`, if `python3.12 -m venv` works on your machine:*

```bash
cd backend
python3.12 -m venv .venv
.venv/bin/pip install -e '.[dev]'
```

Your `PYTHON` is then `.venv/bin/python`.

*Option B — conda, if Option A fails:*

```bash
conda create -y -n roia python=3.12
```

Now find the new env's interpreter and keep that path — it is your `PYTHON`:

```bash
conda env list | grep -w roia
```

That prints the env folder, e.g. `/home/you/anaconda3/envs/roia`. Your `PYTHON` is that
path with `/bin/python` on the end, and you use it **verbatim** from here on:

```bash
cd backend
/home/you/anaconda3/envs/roia/bin/python -m pip install -e '.[dev]'
```

> **If Option A fails** with *"ensurepip is not available … you need to install the
> python3-venv package"*, your system Python is missing the `venv` bootstrap. Either
> `sudo apt install python3.12-venv` and retry, or use Option B — nothing else on this
> page changes.

> **Use the full path. Do not use `conda activate`, and do not use `conda run`.** Both can
> silently give you a *different* Python than the one you asked for:
>
> - `conda activate roia` does not carry from one terminal to the next, and a shell that is
>   only half-activated falls back to the **base** Python — which may be an older version.
>   The install then fails with *"Package 'roia' requires a different Python"*.
> - `conda run -n roia python …` resolves `python` from your `PATH` before the named env.
>   If you already have another conda env active, this quietly runs **that** env's Python
>   and installs `roia` into the wrong place, with no error at all. Verified on this
>   machine: with `know_show` active, `conda run -n roia python -c "import sys;
>   print(sys.executable)"` prints the `know_show` interpreter.
>
> The full path cannot go wrong, which is why every command below uses it.

**Check it worked.** With `PYTHON` set to whichever path you chose:

```bash
$PYTHON --version                                        # expect Python 3.12.x
cd /tmp && $PYTHON -c "import roia; print('roia imports OK')"
```

The `cd /tmp` matters: run that import from inside `backend/` and it prints OK even when the
install failed, because it just finds the `roia/` source folder sitting next to you.

**2. Add your keys**

```bash
cp .env.example .env
```

Now open `backend/.env` in any text editor and fill in the two blank lines:

```
GEMINI_API_KEY=your-key-here
OPENALEX_API_KEY=your-key-here
OPENALEX_MAILTO=your.email@example.com
```

Leave everything else as it is. This file stays on your machine and is never uploaded
anywhere.

**3. Build the web page**

**Check first — this may already be done.** The built page lives in `frontend/dist/`:

```bash
ls frontend/dist/index.html
```

If that file exists, **skip this step entirely**. The backend serves `dist/` directly, so
you do not need Node installed at all to run the app.

Only if it is missing:

```bash
cd ../frontend
nvm use          # skip this line if you don't use nvm
npm install
npm run build
```

That's the setup done. You only do it once.

---

## Part 2 — Running it

### Start it

```bash
cd backend
$PYTHON -m uvicorn roia.api:app_factory --factory --port 8000
```

where `$PYTHON` is the path you settled on in set-up step 1 — `.venv/bin/python` for
Option A, or the full conda path for Option B.

Leave that terminal open — it is the app running. You'll see a line saying
`Uvicorn running on http://127.0.0.1:8000`.

### Open it

Go to <http://localhost:8000> in your browser.

### Stop it

Press `Ctrl+C` in the terminal.

---

## Part 3 — Try it first without using any keys

Before spending a real run, look at a finished one. Open this address:

```
http://localhost:8000/runs/run-001?fixture=run-001&speed=10
```

This replays a real recorded run — you'll see the progress timeline fill in, then the finished
report. It costs nothing, needs no keys, and shows you exactly what to expect.

Drag the sliders. Click the little `e12`-style chips. This is the fastest way to understand
what the tool produces.

---

## Part 4 — Doing a real run

### Step 1 — Fill in the two boxes

On the home page you'll see two fields.

**The grant call.** Either:

- paste the **web address** of a funding call, or
- **upload a PDF** of one

**The researcher's page.** Paste the web address of a public page about the researcher — a lab
page, a university staff page, or a personal academic site.

### A worked example

| Field | Value |
|---|---|
| Grant call | `https://www.rgp.gov.sg/nrf-ar/crp` |
| Researcher page | `https://basurafernando.github.io/` |

This is a Singapore national research grant paired with a researcher based in Singapore — so
eligibility genuinely applies rather than being trivially satisfied. It is a good pair to test
with.

### Step 2 — Press "Analyse"

The app spends about **20 seconds** reading both of your inputs. It doesn't start the real work
yet — it's checking whether your request is clear.

### Step 3 — Answer the questions it asks

Often it will come back with a question or two, because grant pages are rarely about a single
call. For the example above it asks:

> **This page lists 2 grant calls. Which one are you applying to?**
> ○ CRP36 — 14 Sep 2026 to 9 Nov 2026 ○ 2026 Frontier CRP — 23 Mar to 18 May 2026 ○ Not sure

> **The call names 3 funding schemes. Which one is yours?**
> ○ T-CRP ○ CRP36 ○ F-CRP ○ All of them

Pick the ones that apply. If you genuinely don't know, choose *"Not sure"* — the tool will use
everything it found rather than guessing at one.

> **Why does it ask?** Because if it guessed wrong, you'd get a confident, well-written report
> about the wrong grant. It asks now, before starting, and never interrupts once running.

### Step 4 — Watch it work

The page shows a live timeline: which step it's on, what it's looking up, how long each took,
how many sources it has gathered. It looks something like this:

```
  Run started
  ingest              0ms      reuse_probe_documents        +56
  identity            1.2s     resolve_author               +1     Basura Fernando
  author_works        342ms    fetch_author_works           +1
  grant_brief         7.1s     llm_grant_brief                     gemini-3.8-flash
  capabilities        3.1s     llm_capabilities                    gemini-3.8-flash
  candidates          2.5s     llm_candidates                      gemini-3.8-flash
  literature         12.2s     search_literature ×9, fetch_top_works ×3 …
  assessment         98.9s     llm_assessment                      gemini-3.1-pro-preview
  ranking             0ms
  report             16ms
  Run finished
```

The whole thing takes **about two minutes**. The last step is the longest — that's the careful
scoring, and it's worth the wait.

You can safely refresh the page, close the tab, or send the link to a colleague. The run has
its own web address and everything is replayed from the start when you come back.

### Step 5 — Read the report

When the run finishes, the report replaces the timeline. Part 5 below walks through what is on
it and what each part means.

---

## Part 5 — Understanding what you get

### Three ranked directions

Each one shows:

- **A title and an overall score out of 10**, plus a confidence label
- **The problem** — what issue this direction addresses
- **The evidence-backed gap** — what the published literature does *not* currently cover
- **Three strengths and three weaknesses**
- **Nine criteria**, each with a score, a one-line reason, and clickable evidence

### What the numbers mean

The overall score is a weighted average of the seven criteria that were scored, nothing
more. It is not a prediction of whether you'll get funded.

The **nine criteria** are:

| Criterion | The question it answers |
|---|---|
| Grant alignment | Does this fit what the funder actually asked for? |
| Scientific novelty | Is this new, or well-trodden ground? |
| Importance | If it works, does it matter? |
| Applicant fit | Is this researcher the right person for it? |
| Feasibility | Can it realistically be done? |
| Competitive differentiation | *Not scored in this version* |
| Collaboration potential | *Not scored in this version* |
| Impact potential | Who benefits, and how directly? |
| Evidence strength | How well-supported is everything above? |

Two criteria show **"not assessed"**. That is deliberate — they're out of scope for this
version, and the tool says so rather than quietly scoring them zero.

### About the confidence label

**Confidence is not the same as quality.** It tells you how well-*supported* a direction is,
not how good it is.

So a modest direction sitting on a large, well-measured body of literature can honestly be
*high confidence*, while an exciting one that rests on seventeen papers is *low confidence*.
Hover over the label and it tells you which score it came from; the downloadable report says
the same thing near the top.

### The score matrix

A grid of all three directions against all nine criteria, so you can see at a glance where they
differ. Hover any cell for the reason behind that score. The two unscored criteria show `n/a`.

### The weight sliders

Nine sliders sit above the report. If feasibility matters more to you than novelty, drag them
and the cards **and the score matrix re-rank instantly**. Nothing is recalculated on the
server, so it's immediate.

The slider positions are stored in the page address, so you can copy the link and send someone
"here's how it looks if we care most about impact".

Press **Reset to default** to put them back.

### The evidence chips

Every claim carries small chips like `e52` or `e81`. **Click one.** A panel opens showing what
that source is, where it came from, and a link straight to it — the exact page of the exact PDF,
or the record for that paper.

This is the point of the whole tool. If you want to check a claim, you can, in one click.

### Warnings

Yellow boxes at the top tell you when something didn't go perfectly — a page that couldn't be
reached, a quote the tool couldn't match word-for-word in the source, or a direction with
thin evidence behind it.

**These are a feature.** The tool tells you where it's less sure rather than papering over it.
You can dismiss them once you've read them, and they are repeated near the top of the
downloadable report so they travel with it.

### Downloading the report

Every run has a plain-text version at:

```
http://localhost:8000/api/runs/YOUR-RUN-ID/report.md
```

Replace `YOUR-RUN-ID` with the id shown at the top of the report page. It contains the same
content and the same links, in Markdown — good for pasting into a document or an email.

---

## Part 6 — Choosing good inputs

### Good grant call inputs

✅ The landing page of a specific funding call
✅ A page that links to the call's PDF documents
✅ A PDF of the call itself, uploaded directly

### What to avoid

❌ A funder's **home page** — it isn't about one call, so the tool has nothing specific to work
   with
❌ A page behind a **login**, which the tool cannot read
❌ A page that is only an **FAQ** — it usually has no objectives, eligibility or criteria on it

### Good researcher pages

✅ A personal academic site
✅ A university or lab staff profile
✅ Any public page that names the researcher and describes their work

### What to avoid

❌ A page with **no name on it** — the tool needs a name to look up
❌ A **group page listing 30 people** — it won't know which one you mean
❌ A social media profile, which is usually too thin to be useful

### A tip

The tool matches the researcher's name against a public publication database. It shows you who
it matched, marked **"unverified"**. **Glance at that line before reading the rest.** If it
matched the wrong person — which can happen with common names — the applicant-fit scores will
be about somebody else.

---

## Part 7 — If something goes wrong

| What you see | What it means | What to do |
|---|---|---|
| It says a page could not be reached | The grant site blocked it or was down | Download the PDF yourself and upload it instead |
| It matched the wrong researcher | Common name, or a thin profile page | Try a more detailed profile page |
| The report has few sources | The grant page had little readable text | Upload the call's PDF directly |
| A `compressed_scores` warning | All the criteria scored similarly, so the sliders barely change the order | Just re-run it |
| Everything hangs at the start | The backend isn't running | Check the terminal from Part 2 |
| "no run …" in the browser | The run id is wrong, or the app was restarted before the run finished | Start a new run |

---

## Part 8 — Handy commands

**Run it from the terminal instead of the browser:**

```bash
cd backend
$PYTHON -m roia run \
  --grant https://www.rgp.gov.sg/nrf-ar/crp \
  --profile https://basurafernando.github.io/ \
  --out runs/demo
```

It writes `runs/demo/report.json` and `runs/demo/report.md`.

**Check everything still works:**

```bash
cd backend
$PYTHON -m pytest
```

Expect **310 passed, 53 deselected**, in about four minutes. No keys and no network are needed: the project
already excludes the `live` tests (which need credentials) and the `e2e` browser tests
(which need Chromium) from the default run, so plain `pytest` is the safe everyday command.

To opt into those explicitly:

```bash
$PYTHON -m pytest -m live     # needs your API keys, makes real calls
$PYTHON -m pytest -m e2e      # needs Chromium and a built frontend/dist/
```

**See a finished example, no keys needed:**

```
http://localhost:8000/runs/run-001?fixture=run-001&speed=10
```

---

## One thing worth knowing

The tool is built so it **cannot invent a source**. The program does all the fetching and
records where each fact came from; the AI is only allowed to point at those records by number.
It has no box to write a web address in, and anything it writes in ordinary prose is scanned
and stripped of web addresses before it is stored.

So if you see a link in the report, something genuinely retrieved it. That is the guarantee the
whole design exists to protect — and it's why you can click any chip and land on a real page.
