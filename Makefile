.PHONY: install dev test lint format build clean run-help

install:
	pip install .

dev:
	pip install -e . pytest ruff build

test:
	pytest

lint:
	ruff check .

format:
	ruff format .

build:
	python -m build

clean:
	rm -rf build dist .pytest_cache .ruff_cache .coverage htmlcov *.egg-info

run-help:
	legal-music --help
