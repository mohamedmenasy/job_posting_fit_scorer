.PHONY: setup dev test test-live migrate types seed e2e screenshots

setup:
	cd backend && uv sync
	cd frontend && npm ci

# Single uvicorn process only: the evaluation queue lives in memory.
dev:
	trap 'kill 0' EXIT; \
	(cd backend && uv run uvicorn --factory app.main:create_app --host 127.0.0.1 --port 8000 --reload) & \
	(cd frontend && npm run dev) & \
	wait

test:
	cd backend && uv run pytest
	cd frontend && npm run typecheck && npm run lint && npm run build

test-live:
	cd backend && uv run pytest -m live $(ARGS)

migrate:
	cd backend && uv run alembic upgrade head

types:
	cd backend && uv run python -m scripts.export_openapi > openapi.json
	cd frontend && npm run types
	rm backend/openapi.json

seed:
	cd backend && uv run python -m scripts.seed_demo

e2e:
	cd frontend && npm run e2e

screenshots:
	cd frontend && npx playwright test --grep @screenshots
