.PHONY: up down migrate test lint etl analytics quality rag-ingest rag-eval phase4-eval classification-eval web-test web-build demo-eval backup-smoke ci

up:
	docker compose up --build -d db api frontend

down:
	docker compose down

migrate:
	docker compose run --rm api alembic upgrade head

test:
	docker compose run --rm api pytest

lint:
	docker compose run --rm api ruff check .

etl:
	docker compose --profile tools run --rm etl etl --days 7

analytics:
	docker compose --profile tools run --rm etl analytics-refresh

quality:
	docker compose --profile tools run --rm etl data-quality

rag-ingest:
	docker compose run --rm api python -m price_lens.rag.cli $(ARGS)

rag-eval:
	docker compose run --rm api python /app/evals/runners/phase5_rag_eval.py

phase4-eval:
	docker compose run --rm api python /app/evals/runners/phase4_eval.py

classification-eval:
	docker compose run --rm api python /app/evals/runners/phase6_classification_eval.py

web-test:
	docker compose build frontend

web-build: web-test

demo-eval:
	docker compose run --rm api python /app/evals/runners/phase6_release_smoke.py

backup-smoke:
	powershell -ExecutionPolicy Bypass -File scripts/backup-restore-smoke.ps1

ci: lint test phase4-eval rag-eval classification-eval web-test
