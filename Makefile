VERSION=$(shell sed -n 's/__version__ = \"\(.*\)\"/\1/p' ayon_server/version.py)


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
