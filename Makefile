VERSION=$(shell uv run python -m ayon_server --version)

default:
	uv run pre-commit install

check:
	uv version $(VERSION)
	uv run ruff check . --select=I --fix
	uv run ruff format .
	uv run ruff check . --fix
	uv run mypy .

reload:
	@echo "You are in a wrong directory :)"
