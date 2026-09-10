---
description: Change the frontend UI colour theme (primary colour and/or light/dark mode)
argument-hint: "<colour and/or mode, e.g. 'teal', '#7b1fa2', 'dark', 'orange dark'>"
---

## Requested theme: $ARGUMENTS

**If `$ARGUMENTS` is empty:** stop. Read `frontend/src/theme.ts`, show the current
`palette` block, and ask what colour or mode they want. Do not guess.

---

You are changing the UI theme. The only file to edit is `frontend/src/theme.ts`.

1. Read `frontend/src/theme.ts`.
2. Parse `$ARGUMENTS`:
   - A hex value (`#7b1fa2`) → use as-is for `primary.main`.
   - A colour name (`teal`, `orange`, `purple`) → pick a sensible hex (prefer the
     matching MUI palette hue, e.g. `@mui/material/colors`), and say which you chose.
   - The words `dark` or `light` → set `palette.mode` accordingly.
   - Both may appear together (`orange dark`). Missing pieces stay unchanged.
3. Make the smallest possible edit — change only the affected lines, keep the file's
   comment and structure.
4. If switching to `dark`, check `primary.main` still has enough contrast on a dark
   background; nudge it lighter if not, and mention that you did.
5. Do **not** run the dev server. Tell the user: Vite HMR picks the change up live if
   `npm run dev` is already running, otherwise it applies on next start.
6. End by showing the new `palette` block.

Keep the reply short: what changed, the new colour, one line on how to see it.
