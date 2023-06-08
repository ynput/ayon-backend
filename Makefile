default:
	poetry run pre-commit install

check:
	poetry run black .
	poetry run ruff --fix .
	poetry run mypy .
