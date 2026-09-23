# Every target is runnable on a clean checkout: uv resolves and installs as needed.
.PHONY: help check lint format test typecheck schema

help:
	@echo "check      lint, typecheck and test. What CI runs"
	@echo "lint       ruff, including format verification"
	@echo "format     rewrite files to the format lint expects"
	@echo "typecheck  mypy, strict"
	@echo "test       pytest"
	@echo "schema     regenerate titles/schema.json from the models"

check: lint typecheck test

lint:
	uv run ruff check .
	uv run ruff format --check .

format:
	uv run ruff format .
	uv run ruff check --fix .

typecheck:
	uv run mypy

test:
	uv run pytest

schema:
	uv run python -m hostlab.schema
