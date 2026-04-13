.PHONY: install dev test lint format build clean check

install:
	pip install .

dev:
	pip install -e ".[dev]"

test:
	pytest

lint:
	ruff check .

format:
	ruff format .

check: lint test

build:
	python -m build

clean:
	rm -rf build dist .pytest_cache .ruff_cache .coverage htmlcov *.egg-info src/*.egg-info

pipx-install:
	pipx install --force .

pipx-uninstall:
	pipx uninstall legal-music

help:
	@echo "legal-music development commands:"
	@echo "  make dev          - install in editable mode with dev tools"
	@echo "  make test         - run tests"
	@echo "  make lint         - run ruff linter"
	@echo "  make format       - run ruff formatter"
	@echo "  make check        - lint + test"
	@echo "  make build        - build sdist + wheel"
	@echo "  make pipx-install - install via pipx (CLI use)"
	@echo "  make clean        - remove build artifacts"
