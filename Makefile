SHELL := /bin/bash
.DEFAULT_GOAL := help

SERVICES := $(notdir $(wildcard services/*))
COMPOSE  := docker compose
# имя консольной команды сервиса: gateway → gateway, orders → orders-service
bin = $(if $(filter gateway,$(1)),gateway,$(subst _,-,$(1))-service)

ANSIBLE_DIR := infra/ansible
comma := ,
ANSIBLE_ARGS := $(if $(HOST),-i "$(HOST)$(comma)" -e target=all) \
                $(if $(SSH_USER),-e ansible_user=$(SSH_USER)) \
                $(if $(KAFKA),-e kafka_enabled=$(KAFKA))

.PHONY: help env install proto new-service up up-kafka down reset ps logs infra infra-kafka \
        run migration fmt lint typecheck test check smoke server-setup deploy front-dev

help: ## показать команды
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

# ───────────── setup / codegen ─────────────
env: ## создать .env из .env.example (если ещё нет)
	@test -f .env || (cp .env.example .env && echo "created .env")

install: env ## поставить всё (uv sync всего воркспейса, создаст uv.lock)
	uv sync --all-packages

proto: ## сгенерировать Python из contracts/**/*.proto
	uv run python scripts/gen_proto.py

new-service: ## каркас сервиса: make new-service name=orders [entity=Order] [port=50060]
	@test -n "$(name)" || (echo "usage: make new-service name=orders [entity=Order] [port=50060]"; exit 1)
	uv run python scripts/new_service.py $(name) $(if $(entity),--entity $(entity)) $(if $(port),--port $(port))
	uv sync --all-packages

# ───────────── docker ─────────────
up: env ## поднять всё в Docker (без Kafka). Фронт: http://localhost, Swagger: :8000/docs
	KAFKA_ENABLED=false $(COMPOSE) up -d --build --remove-orphans

up-kafka: env ## поднять всё + Kafka (kafka-ui: http://localhost:8081)
	KAFKA_ENABLED=true $(COMPOSE) --profile kafka up -d --build --remove-orphans

down: ## остановить (данные сохраняются)
	$(COMPOSE) --profile kafka down

reset: ## остановить и УДАЛИТЬ данные (volumes)
	$(COMPOSE) --profile kafka down -v

ps: ## статус контейнеров
	$(COMPOSE) --profile kafka ps

logs: ## логи: make logs [s=gateway]
	$(COMPOSE) logs -f --tail=100 $(s)

# ───────────── локальная разработка ─────────────
infra: env ## только Postgres + Redis в Docker, сервисы гоняешь локально через make run
	$(COMPOSE) up -d postgres redis

infra-kafka: env ## Postgres + Redis + Kafka (сервисам: KAFKA_ENABLED=true в .env)
	$(COMPOSE) --profile kafka up -d postgres redis kafka kafka-ui

run: ## запустить сервис локально: make run s=auth | s=gateway [cmd=serve|migrate]
	@test -n "$(s)" || (echo "usage: make run s=<$(SERVICES)>"; exit 1)
	cd services/$(s) && uv run $(call bin,$(s)) $(if $(filter gateway,$(s)),,$(or $(cmd),run))

migration: ## автогенерация миграции: make migration s=auth m="add phone"
	@test -n "$(s)" -a -n "$(m)" || (echo 'usage: make migration s=<service> m="message"'; exit 1)
	cd services/$(s) && uv run $(call bin,$(s)) makemigrations "$(m)"

front-dev: ## фронт с hot reload на :5173 (проксирует /api в localhost:8000)
	cd frontend && (test -d node_modules || npm install) && npm run dev

# ───────────── качество ─────────────
fmt: ## автоформат + автофиксы
	uv run ruff format .
	uv run ruff check --fix .

lint: ## ruff
	uv run ruff check .
	uv run ruff format --check .

typecheck: ## mypy --strict
	uv run mypy packages/platform_common/src $(wildcard services/*/src)

test: ## pytest по всем пакетам (интеграционные тесты сами пропустятся без Postgres)
	@set -e; for d in packages/platform_common $(addprefix services/,$(SERVICES)); do \
		echo "── $$d"; (cd $$d && uv run pytest -q); done

check: lint typecheck test ## всё сразу (как в CI)

smoke: ## e2e по живому стенду: make smoke [URL=http://1.2.3.4]
	uv run python scripts/smoke.py $(or $(URL),http://localhost:8000)

# ───────────── деплой (infra/ansible/README.md) ─────────────
server-setup: ## подготовить сервер: make server-setup HOST=1.2.3.4 SSH_USER=ubuntu
	cd $(ANSIBLE_DIR) && ansible-playbook playbooks/setup.yml $(ANSIBLE_ARGS)

deploy: ## выкатить: make deploy HOST=1.2.3.4 SSH_USER=ubuntu [KAFKA=true]
	cd $(ANSIBLE_DIR) && ansible-playbook playbooks/deploy.yml $(ANSIBLE_ARGS)
