VERSION=$(shell uv run python -m ayon_server --version)

PHONY: default check test test-all test-integration test-api reload

ifneq (,$(wildcard ./.env))
    include .env
    export
endif


default:
	uv run pre-commit install

check:
	uv version $(VERSION)
	uv run ruff check . --select=I --fix
	uv run ruff format .
	uv run ruff check . --fix
	uv run mypy .


test-all: test test-integration test-api

test:
	uv run pytest tests/unit

# Requires Postgres (configured using AYON_POSTGRES_URL)
test-integration:
	uv run pytest tests/integration

# Requires a running server (AYON_API_URL and AYON_API_KEY)
test-api:
	AYON_API_KEY=$(AYON_API_KEY) AYON_API_URL=$(AYON_API_URL) AYON_API_TEST_PROJECT=$(AYON_API_TEST_PROJECT) uv run pytest tests/api

reload:
	@echo "You are in a wrong directory :)"
