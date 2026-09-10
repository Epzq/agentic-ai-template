# Tool Comparison

Three versions of the same idea, compared on one question: **how much can you trust what it tells you?**

| | **A. The template**<br>(`agentic-ai-template-main`) | **B. Our demo**<br>(2 days) | **C. Our full tool**<br>(~15 days) |
|---|---|---|---|
| Time to build | Already exists | 2 days | ~15 days |
| Time per answer | ~1 minute | ~5 minutes | ~6 minutes |
| Can you check its work? | **No** | **Yes** | **Yes** |

---

## The short answer

**Yes — the demo will be meaningfully more accurate than the template.** But the improvement is not "it gets more things right." It is:

> **The template can be wrong without you ever noticing. Our demo cannot.**

That is the whole difference, and it matters more than it sounds.

The template asks an AI model to go and research something, and the model writes back a few paragraphs — including the web links. Those paragraphs usually look excellent. Some of it will be right. But **you have no way to tell which parts**, because nothing was recorded. If it names a paper, you cannot confirm the paper exists. If it gives you a link, nobody checked that the link opens.

Our demo works the other way round. Our own code goes and fetches the pages and the papers first, and writes down what it actually got. The AI is then only allowed to point at those saved items. It is never allowed to write a link itself. So every fact in the report traces back to something the system really downloaded — and you can click through and see it.

For someone deciding where to spend the next three years of their research career, **"probably right but uncheckable" is not good enough.** That is the gap the demo closes.

---

## What mistakes can each one make?

This is the most useful way to compare them.

| Possible mistake | A. Template | B. Our demo | C. Our full tool |
|---|---|---|---|
| Invents a paper that doesn't exist | ⚠️ **Possible** | ✅ Prevented | ✅ Prevented |
| Gives a link that goes nowhere | ⚠️ **Possible** | ✅ Prevented | ✅ Prevented |
| Analyses the **wrong researcher** (same name as someone else) | ⚠️ **Possible** | ⚠️ **Still possible** | ✅ Prevented |
| Says a research gap is open when someone already solved it | ⚠️ **Likely** | ⚠️ Reduced | ✅ Mostly prevented |
| Stretches what a paper actually said | ⚠️ **Possible** | ⚠️ **Still possible** | ✅ Checked |
| Gives a confidence score with no reasoning behind it | ⚠️ **Yes, always** | ✅ Prevented | ✅ Prevented |
| Quietly guesses when information is missing | ⚠️ **Possible** | ✅ Says "unknown" | ✅ Says "unknown" |
| Recommends something even when evidence is thin | ⚠️ **Always will** | ⚠️ Warns you | ✅ Refuses to |

Notice the two rows where **our demo is still weak**. Those are honest, not oversights — they are listed as "not building this yet" in the demo spec, and they are the main reason the full version exists.

---

## What each one has

### A. The template — what it has

- A working end-to-end run today (once a one-line bug is fixed — see below)
- Reads a document you give it (PDF, Word, text)
- Looks up a researcher from their web page
- Searches the web for related grants and competing labs
- Produces a tidy, readable report
- Gives a single "match percentage" between the researcher and the grant
- Clean, well-organised code that is genuinely nice to read and learn from

### A. The template — what it does **not** have

- **No record of where anything came from.** Nothing is saved, so nothing can be checked afterwards
- **No link checking.** The links in the report were written by the AI, not fetched by the system
- **No research-gap analysis at all.** This is the heart of what you asked for, and it is simply absent
- **No check on whether a gap is still open.** It has no access to publication databases, so it cannot see whether the problem was solved last year
- **Only one research direction** — you asked for a ranked list of 3–5
- **The match score is one number the AI made up.** No breakdown, no reasoning you can inspect or disagree with
- **No handling of name confusion.** If two researchers share a name, it may silently mix them up
- **No screen to watch.** It runs in a terminal window with no visible progress and no web page

> ⚠️ **It is also currently broken.** The grant-analysis feature — the reason this template is relevant to you at all — does not even start, because of a one-line mistake left behind by an unfinished code change. Its own automated tests have been failing. I fixed it (all 20 tests now pass), but it tells you something: **this part has never actually been run and checked properly.** Read it for ideas; don't build on it.

---

### B. Our demo (2 days) — what it has

- Everything the template does, **plus real evidence**
- **Our own code fetches every page**, and pulls the real database record and summary for every paper it cites — saving what it got, with the time it was fetched
- **Every link in the report came from a page the system downloaded or a database record it retrieved.** None were written by the AI
- **The AI is structurally blocked from writing links.** It can only point at things already saved — this is enforced by an automated test, not by asking nicely
- Uses a **real research-paper database** (OpenAlex) — so real publication counts, real years, real citation numbers
- **Three ranked research directions**, not one
- **Nine separate scores** per direction instead of one mystery percentage
- **Sliders you can move to change what matters to you** — the ranking reshuffles instantly, in front of you
- **A live screen showing what it is doing**, second by second: which search it is running, which paper record it is pulling
- Says **"unknown"** instead of guessing when something can't be found
- Keeps working and warns you if a page won't load, instead of crashing

### B. Our demo — what it does **not** have

- **No check that it found the right person.** If your name is common, it may build the whole report around a different researcher with the same name. *This is the biggest weakness of the demo.*
- **Only a light check on whether a gap is still open.** It looks at publication trends and citation counts, but it can miss work that solved the problem while calling it something else
- **It reads paper summaries, not full papers.** It sees titles, years, citation counts and abstracts — not the papers' own "limitations" sections
- **No check that a quote actually supports the claim built on it.** The quote will be real; the conclusion drawn from it might stretch too far
- **No competitor or collaborator analysis** — that whole section is skipped
- **Does not remember past runs**, and cannot export to PDF or Word
- Chooses **not** to build several safety checks on purpose, to fit in two days

---

### C. Our full tool (~15 days) — what it adds on top of the demo

- **Confirms the right researcher.** Matches the lab website to the institution, then to the correct person, and checks the result independently. If it's unsure, it asks you instead of guessing
- **Four separate checks on whether a gap is really still open** — including deliberately searching for work that *solved* it, using different wording, in case another research community renamed the problem
- **Refuses to say a gap is open just because it found nothing.** Finding nothing is treated as "don't know", never as proof
- **Checks that each quote genuinely supports the claim** attached to it, and downgrades it if not
- **Shows the supporting quote directly under each claim**, so you can judge it yourself in one second
- **Marks the difference between "we read this paper" and "we only saw its title"** — and won't let a claim about a paper's contents rest on a title alone
- **Full competitor and collaborator analysis:** who else is working on this, how crowded it is, and what expertise you'd need to partner for
- **Refuses to recommend a direction when the evidence is too thin**, and tells you exactly how thin
- **Tests whether the ranking is stable** — if two directions are too close to separate honestly, it says so rather than declaring a winner
- Remembers past runs, exports the report, and handles scanned/awkward PDFs

---

## Honest verdict

**Is the demo better than the template? Yes, clearly — on the thing that matters.**

The template produces something that *reads* well. Our demo produces something you can *defend*. If a colleague points at a line in the report and asks "how do you know that?", the demo has an answer for every line and the template has an answer for none.

**But do not oversell the demo.** It still has two real weaknesses: it might analyse the wrong person, and it might tell you a gap is open when it isn't. Both are fixed in the full version, and both should be said out loud when you show it.

**A fair way to describe each:**

| | Best described as |
|---|---|
| **A. Template** | A quick first impression. Useful for a rough sense of direction in one minute. Not something to make a decision on. |
| **B. Our demo** | A real research assistant with its working shown — but still learning. Trust the sources completely; double-check the person and the gap yourself. |
| **C. Full tool** | Something a researcher could genuinely rely on to shortlist where to spend the next three years. |

---

## One last point worth understanding

The template will almost never *look* bad. Its mistakes are invisible — a made-up paper looks exactly like a real one in a nicely formatted report.

Our demo will sometimes look *worse*, because it says "unknown", or warns that a page wouldn't load, or admits the evidence is thin.

**That is the improvement, not a flaw.** A tool that tells you when it doesn't know is far more useful than one that always sounds confident.
