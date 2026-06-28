.DEFAULT_GOAL := help
COMPOSE := docker compose
BACKEND := cd backend &&
FRONTEND := cd frontend &&

# --- Native (no-Docker) toolchain -------------------------------------------
# Backend runs in a project-local virtualenv so `make` works without any global
# Python packages. `uv` is used when available (much faster), else stdlib venv.
VENV := backend/.venv
VBIN := .venv/bin
STAMP := $(VENV)/.install-stamp
UV := $(shell command -v uv 2>/dev/null)

# Settings + process bookkeeping for native runs.
DJANGO_ENV := DJANGO_SETTINGS_MODULE=config.settings.dev
RUN := .run

.PHONY: help
help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| sort \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-22s\033[0m %s\n", $$1, $$2}'

# ===========================================================================
# Native dev (DEFAULT). The app runs on your machine; only the infrastructure
# (Postgres + Redis) runs in Docker. Docker full-stack lives under `docker-*`.
# ===========================================================================

# --- One-time / on-demand setup ---------------------------------------------
$(STAMP): backend/pyproject.toml
	@echo ">> creating virtualenv and installing backend deps (this is cached)"
ifeq ($(UV),)
	$(BACKEND) python3 -m venv .venv \
		&& .venv/bin/python -m pip install -U pip \
		&& .venv/bin/python -m pip install -e ".[dev,observability]"
else
	$(BACKEND) $(UV) venv .venv --allow-existing && $(UV) pip install -e ".[dev,observability]"
endif
	@touch $@

.PHONY: install setup env
install: $(STAMP) ## Create the backend virtualenv and install deps (uv if present)

env: ## Generate backend/.env with sane native defaults (never overwrites)
	@if [ -f backend/.env ]; then \
		echo "backend/.env already exists; leaving it untouched"; \
	else \
		cp .env.example backend/.env && echo "wrote backend/.env from .env.example"; \
	fi

setup: install env ## One-time local setup: virtualenv + .env

# --- Infrastructure (Docker, infra only) ------------------------------------
.PHONY: infra-up infra-down
infra-up: ## Start ONLY Postgres + Redis in Docker (waits until healthy)
	$(COMPOSE) up -d --wait db redis

infra-down: ## Stop the infra containers (keeps the data volume)
	$(COMPOSE) stop db redis

# --- Run the app natively ----------------------------------------------------
.PHONY: up down restart logs ps
up: $(STAMP) env infra-up migrate ## Run the app natively (backend, worker, beat, frontend)
	@mkdir -p $(RUN)
	@echo ">> starting backend  -> http://127.0.0.1:8000"
	@( $(BACKEND) exec env $(DJANGO_ENV) $(VBIN)/python manage.py runserver 127.0.0.1:8000 ) \
		>> $(RUN)/backend.log 2>&1 & echo $$! > $(RUN)/backend.pid
	@echo ">> starting celery worker"
	@( $(BACKEND) exec env $(DJANGO_ENV) $(VBIN)/celery -A config worker -l info ) \
		>> $(RUN)/worker.log 2>&1 & echo $$! > $(RUN)/worker.pid
	@echo ">> starting celery beat"
	@( $(BACKEND) exec env $(DJANGO_ENV) $(VBIN)/celery -A config beat -l info ) \
		>> $(RUN)/beat.log 2>&1 & echo $$! > $(RUN)/beat.pid
	@if [ -d frontend/node_modules ]; then \
		echo ">> starting frontend -> http://127.0.0.1:3000"; \
		( $(FRONTEND) exec npm run dev ) >> $(RUN)/frontend.log 2>&1 & echo $$! > $(RUN)/frontend.pid; \
	else \
		echo ">> frontend deps missing; run 'make fe-install' first (skipping frontend)"; \
	fi
	@echo ">> up. tail logs with 'make logs', stop with 'make down'."

down: ## Stop the native app processes and the infra containers
	-@for f in $(RUN)/*.pid; do \
		[ -f "$$f" ] || continue; \
		pid=$$(cat "$$f"); \
		if kill "$$pid" 2>/dev/null; then echo "stopped $$(basename $$f .pid) (pid $$pid)"; fi; \
		rm -f "$$f"; \
	done
	@$(MAKE) --no-print-directory infra-down

restart: down up ## Restart the native stack

logs: ## Tail the native process logs
	@tail -n 100 -f $(RUN)/*.log 2>/dev/null || echo "no logs yet; run 'make up'"

ps: ## Show the status of native processes
	@found=0; for f in $(RUN)/*.pid; do \
		[ -f "$$f" ] || continue; found=1; pid=$$(cat "$$f"); \
		if kill -0 "$$pid" 2>/dev/null; then echo "$$(basename $$f .pid): running (pid $$pid)"; \
		else echo "$$(basename $$f .pid): not running"; fi; \
	done; [ "$$found" = 1 ] || echo "no native processes; run 'make up'"

# --- Database (native) -------------------------------------------------------
.PHONY: migrate makemigrations seed shell superuser
migrate: $(STAMP) ## Apply database migrations (native)
	$(BACKEND) env $(DJANGO_ENV) $(VBIN)/python manage.py migrate

makemigrations: $(STAMP) ## Create new migrations (native)
	$(BACKEND) env $(DJANGO_ENV) $(VBIN)/python manage.py makemigrations

seed: migrate ## Load sample data (placeholder until fixtures exist)

shell: $(STAMP) ## Open a Django shell (native)
	$(BACKEND) env $(DJANGO_ENV) $(VBIN)/python manage.py shell

superuser: $(STAMP) ## Create an admin user (native)
	$(BACKEND) env $(DJANGO_ENV) $(VBIN)/python manage.py createsuperuser

# --- Backend quality (native; mirrors what CI checks) -----------------------
.PHONY: lint format type test test-unit test-integration coverage security check
lint: $(STAMP) ## Lint the backend (ruff)
	$(BACKEND) $(VBIN)/ruff check .

format: $(STAMP) ## Auto-format the backend (ruff)
	$(BACKEND) $(VBIN)/ruff format . && $(BACKEND) $(VBIN)/ruff check --fix .

type: $(STAMP) ## Type-check the backend (mypy)
	$(BACKEND) $(VBIN)/mypy src config

test: $(STAMP) ## Run all backend tests with coverage
	$(BACKEND) $(VBIN)/pytest

test-unit: $(STAMP) ## Run fast unit tests (no database)
	$(BACKEND) $(VBIN)/pytest tests/unit -m "not integration" --no-cov

test-integration: $(STAMP) ## Run integration tests
	$(BACKEND) $(VBIN)/pytest tests/integration -m integration

coverage: test ## Run backend tests and enforce the coverage threshold

security: $(STAMP) ## Run backend security scanners (bandit + pip-audit)
	$(BACKEND) $(VBIN)/bandit -q -r src config && $(BACKEND) $(VBIN)/pip-audit

check: lint type test ## Quick local quality gate (backend lint + type + test)

# ===========================================================================
# Docker full-stack (everything in containers)
# ===========================================================================
.PHONY: docker-build docker-up docker-down docker-restart docker-logs docker-ps
docker-build: ## Build all Docker images
	$(COMPOSE) build

docker-up: ## Start the full dev stack in Docker
	$(COMPOSE) up -d

docker-down: ## Stop and remove all containers
	$(COMPOSE) down

docker-restart: docker-down docker-up ## Restart the full Docker stack

docker-logs: ## Tail Docker service logs
	$(COMPOSE) logs -f

docker-ps: ## List running Docker services
	$(COMPOSE) ps

.PHONY: docker-shell docker-bash docker-migrate docker-makemigrations docker-superuser
docker-shell: ## Open a Django shell in the backend container
	$(COMPOSE) exec backend python manage.py shell

docker-bash: ## Open a shell in the backend container
	$(COMPOSE) exec backend bash

docker-migrate: ## Apply migrations in the backend container
	$(COMPOSE) exec backend python manage.py migrate

docker-makemigrations: ## Create migrations in the backend container
	$(COMPOSE) exec backend python manage.py makemigrations

docker-superuser: ## Create an admin user in the backend container
	$(COMPOSE) exec backend python manage.py createsuperuser

# ===========================================================================
# Frontend quality
# ===========================================================================
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

# ===========================================================================
# Aggregate / docs
# ===========================================================================
.PHONY: ci docs
ci: lint type coverage fe-lint fe-type fe-test ## Full quality gate (backend + frontend)

docs: ## Serve project documentation
	mkdocs serve
