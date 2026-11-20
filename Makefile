.PHONY: up down logs migrate run backfill test shell-db

up:
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f

migrate:
	alembic upgrade head

run:
	python scripts/run_pipeline.py

backfill:
	python scripts/backfill.py --days 7

test:
	pytest -q

shell-db:
	docker compose exec db psql -U brief -d brief
