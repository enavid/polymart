.DEFAULT_GOAL := help
COMPOSE := docker compose
BACKEND := cd backend &&
FRONTEND := cd frontend &&

.PHONY: help
help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| sort \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-22s\033[0m %s\n", $$1, $$2}'

# ---------------------------------------------------------------------------
# Docker lifecycle
# ---------------------------------------------------------------------------
.PHONY: build up down restart logs ps
build: ## Build all Docker images
	$(COMPOSE) build

up: ## Start the full dev stack
	$(COMPOSE) up -d

down: ## Stop and remove containers
	$(COMPOSE) down

restart: down up ## Restart the stack

logs: ## Tail service logs
	$(COMPOSE) logs -f

ps: ## List running services
	$(COMPOSE) ps

.PHONY: shell bash migrate makemigrations seed superuser
shell: ## Open a Django shell in the backend container
	$(COMPOSE) exec backend python manage.py shell

bash: ## Open a shell in the backend container
	$(COMPOSE) exec backend bash

migrate: ## Apply database migrations
	$(COMPOSE) exec backend python manage.py migrate

makemigrations: ## Create new migrations
	$(COMPOSE) exec backend python manage.py makemigrations

seed: ## Load sample data (placeholder until fixtures exist)
	$(COMPOSE) exec backend python manage.py migrate

superuser: ## Create an admin user
	$(COMPOSE) exec backend python manage.py createsuperuser

# ---------------------------------------------------------------------------
# Backend quality (run natively; the same targets are used by CI)
# ---------------------------------------------------------------------------
.PHONY: install lint format type test test-unit test-integration coverage security
install: ## Install backend dev dependencies
	$(BACKEND) pip install -e ".[dev,observability]"

lint: ## Lint the backend (ruff)
	$(BACKEND) ruff check .

format: ## Auto-format the backend (ruff)
	$(BACKEND) ruff format . && ruff check --fix .

type: ## Type-check the backend (mypy)
	$(BACKEND) mypy src config

test: ## Run all backend tests with coverage
	$(BACKEND) pytest

test-unit: ## Run fast unit tests (no database)
	$(BACKEND) pytest tests/unit -m "not integration" --no-cov

test-integration: ## Run integration tests (database)
	$(BACKEND) pytest tests/integration -m integration

coverage: ## Run backend tests and enforce coverage threshold
	$(BACKEND) pytest

security: ## Run backend security scanners
	$(BACKEND) bandit -q -r src config && cd backend && pip-audit

# ---------------------------------------------------------------------------
# Frontend quality
# ---------------------------------------------------------------------------
.PHONY: fe-install fe-lint fe-type fe-test fe-build e2e
fe-install: ## Install frontend dependencies
	$(FRONTEND) npm install

fe-lint: ## Lint the frontend
	$(FRONTEND) npm run lint

fe-type: ## Type-check the frontend
	$(FRONTEND) npm run typecheck

fe-test: ## Run frontend unit tests (vitest)
	$(FRONTEND) npm run test

fe-build: ## Build the frontend
	$(FRONTEND) npm run build

e2e: ## Run end-to-end tests (playwright)
	$(FRONTEND) npm run e2e

# ---------------------------------------------------------------------------
# Aggregate / docs
# ---------------------------------------------------------------------------
.PHONY: ci docs
ci: lint type coverage fe-lint fe-type fe-test ## Run the full CI quality gate locally

docs: ## Serve project documentation
	mkdocs serve
