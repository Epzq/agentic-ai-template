# Reference

`config_pattern.py` — the pydantic-settings pattern lifted from `agentic-ai-template-main`,
which `demo-spec.md` §5 says to port. Adapt the prefix to `ROIA_` and add our own fields.

The rest of that template was deliberately not carried over — see `tool-comparison.md`
for why (its research layer returns model-authored URLs, which violates our core rule).
The original archive is at `~/Downloads/agentic-ai-template-main.zip` if you want to read it.

Known bug in that template, in case you ever go back to it: `analyst.py` imports
`profile_researcher` from `.gemini`, but it is defined in `.tools` — `pytest` fails at
collection and the grant-fit analyst cannot start.
