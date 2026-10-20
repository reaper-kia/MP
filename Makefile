SHELL := /bin/bash
.DEFAULT_GOAL := help

# все папки в services/ — это сервисы
SERVICES := $(notdir $(wildcard services/*))
COMPOSE := docker compose

ANSIBLE_DIR := infra/ansible
comma := ,
ANSIBLE_ARGS := $(if $(HOST),-i "$(HOST)$(comma)" -e target=all) $(if $(SSH_USER),-e ansible_user=$(SSH_USER)) \
                $(if $(HTTP_PORT),-e http_port=$(HTTP_PORT))
# Ключи API для сервера: из окружения, а если не заданы — из локального .env.
# LLM_PROVIDER из .env НЕ берём: локально там ollama, а на сервере модели нет (stub из group_vars).
DEPLOY_KEYS := VK_SERVICE_TOKEN YC_FOLDER_ID YC_API_KEY YC_SEARCH_API_KEY
deploy_env = $(foreach k,$(DEPLOY_KEYS),$(k)="$${$(k):-$$(grep -s '^$(k)=' .env | cut -d= -f2-)}")
# Адрес сайта на сервере из inventory (для seed/smoke после деплоя)
SERVER_URL ?= http://109.196.167.204:8080

.PHONY: help env install lock proto docs mock up down reset ps logs db run migration \
        lint fmt typecheck test check smoke seed front-dev deploy release vk-login

help: ## список команд
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

# ───────── установка и кодогенерация ─────────
env: ## создать .env (compose) и services/<сервис>/.env (локальный запуск) из .env.example
	@test -f .env || (cp .env.example .env && echo "created .env")
	@for s in $(SERVICES); do test -f services/$$s/.env || (cp services/$$s/.env.example services/$$s/.env && echo "created services/$$s/.env"); done

install: env ## uv sync в каждом сервисе
	@for s in $(SERVICES); do echo "── $$s"; (cd services/$$s && uv sync) || exit 1; done

lock: ## uv lock в каждом сервисе (uv.lock коммитим)
	@for s in $(SERVICES); do (cd services/$$s && uv lock) || exit 1; done

proto: ## contracts/*.proto → packages/platform_contracts + справочники docs/
	uv run --project services/gateway python scripts/generate_proto.py
	@$(MAKE) --no-print-directory docs

docs: ## docs/API.md, docs/api-types.ts, docs/GRPC.md из контрактов
	uv run --project services/gateway python scripts/gen_api_docs.py
	uv run --project services/gateway python scripts/gen_grpc_docs.py

mock: ## мок HTTP API для фронта по openapi.yaml: http://localhost:4010
	npx @stoplight/prism-cli@5 mock contracts/http/openapi.yaml -p 4010

# ───────── docker ─────────
up: env ## собрать и поднять всё. Фронт: http://localhost, Swagger: http://localhost:8000/docs
	$(COMPOSE) up -d --build

down: ## остановить (данные сохраняются)
	$(COMPOSE) down

reset: ## остановить и удалить данные БД
	$(COMPOSE) down -v

ps: ## статус контейнеров
	$(COMPOSE) ps

logs: ## логи: make logs [s=gateway]
	$(COMPOSE) logs -f --tail=100 $(s)

# ───────── локальная разработка ─────────
db: env ## поднять только базы (*_db) — сервисы запускаешь локально через make run
	$(COMPOSE) up -d $$($(COMPOSE) config --services | grep '_db$$')

run: ## запустить сервис локально: make run s=search_service | s=gateway
	@test -n "$(s)" || (echo "usage: make run s=<$(SERVICES)>"; exit 1)
	@if [ "$(s)" = "gateway" ]; then \
		cd services/gateway && uv run uvicorn gateway.main:app --reload --port 8000; \
	else \
		cd services/$(s) && (test ! -f alembic.ini || uv run alembic upgrade head) && uv run $(subst _,-,$(s)); \
	fi

migration: ## новая миграция: make migration s=search_service m="init"
	@test -n "$(s)" -a -n "$(m)" || (echo 'usage: make migration s=<service> m="message"'; exit 1)
	cd services/$(s) && uv run alembic revision --autogenerate -m "$(m)"

front-dev: ## фронт с hot reload на :5173 (проксирует /api на gateway 127.0.0.1:8000)
	cd frontend && (test -d node_modules || npm install) && VITE_API_TARGET=http://127.0.0.1:8000 npm run dev

# ───────── проверки ─────────
fmt: ## автоформат
	@for s in $(SERVICES); do (cd services/$$s && uv run ruff format . && uv run ruff check --fix .); done

lint: ## ruff
	@for s in $(SERVICES); do echo "── $$s"; (cd services/$$s && uv run ruff check . && uv run ruff format --check .) || exit 1; done

typecheck: ## mypy --strict
	@for s in $(SERVICES); do echo "── $$s"; (cd services/$$s && uv run mypy src) || exit 1; done

test: ## pytest
	@for s in $(SERVICES); do echo "── $$s"; (cd services/$$s && uv run pytest -q) || exit 1; done

check: lint typecheck test ## всё сразу (как в CI)

smoke: ## сквозная проверка живого стенда: make smoke [URL=http://1.2.3.4]
	uv run --project services/gateway python scripts/smoke.py $(or $(URL),http://localhost:8000)

seed: ## каталог источников из seed/sources.xlsx: make seed [URL=http://1.2.3.4]
	python3 scripts/seed_sources.py $(or $(URL),http://localhost:8000)

# ───────── деплой ─────────
deploy: ## выкатить на сервер из inventory (или HOST=1.2.3.4 SSH_USER=ubuntu [HTTP_PORT=8080])
	$(deploy_env) bash -c 'cd $(ANSIBLE_DIR) && ansible-playbook playbooks/deploy.yml $(ANSIBLE_ARGS)'

release: ## деплой + каталог источников + smoke: make release [SERVER_URL=http://1.2.3.4:8080]
	$(MAKE) deploy
	$(MAKE) seed URL=$(SERVER_URL)
	$(MAKE) smoke URL=$(SERVER_URL)

vk-login: ## вход VK ID для сервера (свой токен, обновляется сам): make vk-login HOST=1.2.3.4 SSH_USER=ubuntu
	@test -n "$(HOST)" || (echo "укажи HOST=…" && exit 1)
	ssh -t $(or $(SSH_USER),ubuntu)@$(HOST) 'cd /opt/mp && sudo python3 scripts/vk_token.py && sudo docker compose restart collector_service'

