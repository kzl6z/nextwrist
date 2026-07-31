.PHONY: install migrate serve up down logs test lint ingest

install:          ## Installe les dependances dans un environnement local
	uv sync --extra dev

migrate:          ## Applique les migrations SQL
	uv run nova db migrate

serve:            ## Lance l'API Nova en local (rechargement automatique)
	uv run uvicorn nova.api.app:app --reload --port 8100

up:               ## Demarre Postgres + Nova + Open WebUI
	docker compose up -d

down:             ## Arrete tout (les donnees sont conservees)
	docker compose down

logs:
	docker compose logs -f

test:              ## Lance les tests (migrate d'abord, sinon l'integration saute)
	uv run nova db migrate && uv run pytest -q

lint:
	uv run ruff check src tests && uv run ruff format --check src tests

ingest:           ## make ingest DIR=./data/documents
	uv run nova ingest $(DIR)
