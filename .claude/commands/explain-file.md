---
description: Explain what one source file does in plain English, and point at its tests
argument-hint: "<path to a file, e.g. backend/roia/ranking.py>"
---

## The file: $ARGUMENTS

**If `$ARGUMENTS` is empty or the path does not exist:** stop. Say so, list the
Python modules under `backend/roia/`, and ask which one they meant.

---

You are explaining one file to someone learning this codebase. Do not change anything.

1. Read `$ARGUMENTS` in full.
2. Say in **two sentences** what this file is for and who calls it.
3. List its public functions/classes — name, one line each on what it does.
4. Find its tests (look in `backend/tests/` for a matching name) and say what they cover.
5. Note anything surprising: a workaround, a `TODO`, a comment explaining a past bug.

Keep it under 30 lines. Plain English — no path soup unless it clarifies something.
