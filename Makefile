VERSION=$(shell sed -n 's/__version__ = \"\(.*\)\"/\1/p' ayon_server/version.py)


default:
	poetry run pre-commit install

check:
	sed -i "s/^version = \".*\"/version = \"$(VERSION)\"/" pyproject.toml
	poetry run ruff check . --select=I --fix
	poetry run ruff format .
	poetry run ruff check . --fix
	poetry run mypy .

reload:
	@echo "You are in a wrong directory :)"
