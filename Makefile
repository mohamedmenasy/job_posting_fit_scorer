.PHONY: setup dev test test-live migrate

setup:
	cd backend && uv sync

# Single uvicorn process only: the evaluation queue lives in memory.
dev:
	cd backend && uv run uvicorn --factory app.main:create_app --host 127.0.0.1 --port 8000 --reload

test:
	cd backend && uv run pytest

test-live:
	cd backend && uv run pytest -m live

migrate:
	cd backend && uv run alembic upgrade head
