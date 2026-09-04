.PHONY: install lint fmt test run

# Use uv if it's available, otherwise fall back to plain pip.
UV := $(shell command -v uv 2>/dev/null)

install:
ifdef UV
	uv pip install -e ".[dev]"
else
	python -m pip install -e ".[dev]"
endif

lint:
	ruff check src tests
	mypy src

fmt:
	ruff check --fix src tests
	ruff format src tests

test:
	pytest

run:
	agentic-ai
