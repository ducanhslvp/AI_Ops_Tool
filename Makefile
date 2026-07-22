.PHONY: setup test lint build migrate seed run

setup:
	cd backend && python -m pip install -e ".[dev]"
	cd ShadcnTemplateFE && npm ci

test:
	cd backend && python -m pytest
	cd ShadcnTemplateFE && npm test

lint:
	cd backend && python -m ruff check app tests ../scripts
	cd ShadcnTemplateFE && npm run lint

build:
	cd ShadcnTemplateFE && npm run build

migrate:
	cd backend && python -m alembic upgrade head

seed:
	cd backend && python ../scripts/seed_backend.py

run:
	./scripts/run_all.sh
