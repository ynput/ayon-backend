default:
	poetry run pre-commit install

check:
	poetry run black .
	poetry run ruff .
	poetry run mypy .
