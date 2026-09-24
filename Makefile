SHELL := /bin/bash
DBT := dbt --no-use-colors
DBT_DIRS := --project-dir warehouse --profiles-dir warehouse

.PHONY: help up down install demo round1 round2 build test lint docs airflow snowflake-parse clean

help:
	@grep -E '^[a-z0-9-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-16s %s\n", $$1, $$2}'

up: ## start Postgres
	docker compose up -d --wait postgres

down: ## stop everything and delete the volume
	docker compose --profile airflow down -v

install: ## install the package and dbt dependencies
	pip install -e ".[dev]"
	$(DBT) deps $(DBT_DIRS)

demo: up ## the whole story, from an empty warehouse
	campcommand reset --yes
	campcommand bootstrap
	@$(MAKE) --no-print-directory round1 round2

round1:
	@echo; echo "== Round 1: three camps send their first exports; devices sync a season of events"
	campcommand generate
	campcommand ingest
	campcommand sync
	$(DBT) build $(DBT_DIRS) --quiet
	campcommand status

round2:
	@echo; echo "== Round 2: the camps fix what their error reports flagged and export again"
	campcommand generate --round 2
	campcommand ingest
	$(DBT) build $(DBT_DIRS) --quiet
	campcommand status

build: ## dbt build
	$(DBT) build $(DBT_DIRS)

test: ## unit and integration tests (integration needs `make up`)
	pytest -v

lint:
	ruff check src tests airflow
	ruff format --check src tests airflow
	sqlfluff lint warehouse/models

docs: ## generate and serve dbt docs
	$(DBT) docs generate $(DBT_DIRS)
	$(DBT) docs serve $(DBT_DIRS)

airflow: up ## Airflow 3 standalone at localhost:8080
	docker compose --profile airflow up --build airflow

snowflake-parse: ## check the project renders for the Snowflake adapter (no account needed)
	DBT_TARGET=snowflake SNOWFLAKE_ACCOUNT=placeholder $(DBT) parse $(DBT_DIRS)

clean:
	rm -rf warehouse/target warehouse/dbt_packages warehouse/logs landing reports
