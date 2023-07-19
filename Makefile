VERSION=$(shell poetry run python -c "import ayon_server; print(ayon_server.__version__, end='')")


default:
	poetry run pre-commit install

check:
	sed -i "s/^version = \".*\"/version = \"$(VERSION)\"/" pyproject.toml
	poetry run black .
	poetry run ruff --fix .
	poetry run mypy .
