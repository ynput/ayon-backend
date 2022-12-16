default:
	poetry run pre-commit install

check:
	poetry run isort .
	poetry run black .
	poetry run flake8 .
	poetry run mypy .
