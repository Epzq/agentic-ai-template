# Execution Agent Prompt

**This file is a pointer. The prompt itself now lives in
[`.claude/commands/execute-workitem.md`](.claude/commands/execute-workitem.md) as a slash command,
so there is one copy and it cannot drift.**

## Use it

```
/execute-workitem 1.0        # or 2.4a, or WI-1.6c — the WI- prefix is optional
```

The command implements **exactly one work item** from `execution-plan.md`, end to end:

| Step | |
|---|---|
| 1 | Orient — read the item, its ACs, its contracts, and the `STATUS` lines of completed items |
| 2 | Plan — state the files, functions and tests before writing any |
| 3 | Implement |
| 4 | **Self-review** — a concrete checklist, not a vibe |
| 5 | Test — `pytest` always, plus `curl` for API items and Playwright for UI items |
| 6 | Self-correct — fix the code, never weaken the test |
| 7 | **Mark done** — update the Progress table and the item's `STATUS` line |
| 8 | Commit |

Run one work item per session, in the order given by the critical path in `execution-plan.md`.
Called with no argument, it prints the Progress table and asks which item you want.

## The other two commands

| Command | For |
|---|---|
| `/explain-app <question>` | Understanding the app. Answers from the docs and the code, marking demo vs full-design throughout |
| `/fix-in-app <requirement>` | Changing the app. Surfaces conflicts, asks before deciding, writes the work item, then calls `/execute-workitem` |

`/fix-in-app` is the front door for a change request: it produces the work item that
`/execute-workitem` then implements. Going straight to `/execute-workitem` with a new idea skips
the agreement step, and the work item is the only record of what was agreed.

## To edit the prompt

Edit `.claude/commands/execute-workitem.md`. Do not copy it back here.
