# Contributing

Thanks for taking the time to contribute.

## Development setup

With [uv](https://docs.astral.sh/uv/):

```bash
uv venv
uv pip install -e ".[dev]"
cp .env.example .env   # add your API key
```

Or with plain pip: `python -m venv .venv && source .venv/bin/activate && make install`.

## Before opening a PR

```bash
make fmt    # auto-format + autofix lint
make lint   # ruff + mypy, must pass
make test   # pytest, must pass
```

`make` targets assume the venv is on `PATH` (`source .venv/bin/activate`). If you
don't activate it, run the tools directly: `uv run ruff check src tests`,
`uv run mypy src`, `uv run pytest`.

- Keep the core (`src/agentic_ai/`) small and readable - it is meant to be read start to finish.
- New tools go in `tools.py` with a one-line docstring and a unit test in `tests/test_tools.py`.
- Tests must not make network calls unless marked `@pytest.mark.network` (deselected by default).
- Conventional commit messages (`feat:`, `fix:`, `docs:`, ...) are appreciated but not required.

## Reporting bugs

Open an issue with the smallest snippet that reproduces the problem, the full
traceback, and your `langchain` / `langgraph` versions (`pip show langchain langgraph`).
