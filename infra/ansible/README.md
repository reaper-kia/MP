# Деплой

Нужно у себя: `ansible`, `rsync`, `sshpass` (Arch: `pacman -S ansible rsync sshpass`).
На сервере: Ubuntu 22.04+ / Debian 12+, SSH-доступ пользователем с sudo.

Сервер команды прописан в `inventory/dev.yml` (`109.196.167.204`, пользователь `team-04`, сайт на
порту 8080 — порт 80 занят системным nginx). Ключи API берутся из локального `.env`. Всё одной
командой:

```bash
ANSIBLE_ASK_PASS=True make release   # выкатка + каталог источников + smoke (= deploy && seed && smoke)
ANSIBLE_ASK_PASS=True make deploy    # только выкатить
```

`ANSIBLE_ASK_PASS=True` — вход по паролю (спросит один раз); заработает вход по ключу — переменная не
нужна. Повторный запуск безопасен: БД, `.env` и токены на сервере не теряются, `make seed` пропускает
уже добавленные источники.

## Роли по порядку

| Роль | Что делает |
|---|---|
| `common` | проверка SSH, git / curl / rsync |
| `docker` | Docker + compose, если их нет; уже установленный Docker и чужой `daemon.json` не трогает; базовые образы — с Docker Hub или с зеркала `mirror.gcr.io` (`docker_base_images`) |
| `sync` | архив проекта (без `.git`, `.venv`, `node_modules`, `.env`, секретов) → `/tmp` на сервере → `rsync --delete` в `/opt/mp` |
| `env` | `/opt/mp/.env` из шаблона (`roles/env/templates/env.j2`, root, 0600); пароль БД генерируется один раз и хранится в `infra/ansible/.secrets/` |
| `start` | порт сайта в ufw, `docker compose up -d --build` классическим сборщиком (без Docker Hub), ждёт `/health/ready` |

Отдельный плейбук `playbooks/tunnel.yml` (`make llm-tunnel-server`) — приём обратного SSH-туннеля
Ollama с ноутбука команды: ключ туннеля в `authorized_keys` с ограничением (только этот `-R`, без
shell), `GatewayPorts clientspecified` только для пользователя деплоя (с проверкой `sshd -t` и
откатом), правило ufw из docker-подсетей к `172.17.0.1:11435`. Ноутбук — `make llm-tunnel-install`,
проверка — `make llm-tunnel-status`. Подробно — `services/ml_service/README.md`.

## Что уходит на сервер

- Ключи площадок и API — из окружения или локального `.env` машины деплоя (`DEPLOY_KEYS` в
  `Makefile`: `VK_SERVICE_TOKEN`, `YC_*`, `MAX_BOT_TOKEN`, `MAX_API_URL`, `HTTP_CA_BUNDLE`). В git их нет.
- Настройки — `playbooks/group_vars/all.yml`: `COLLECTOR_FAKE=false` всегда; модели —
  `LLM_PROVIDER=ollama,yandex` (ноутбук через туннель → Яндекс, если есть `YC_API_KEY` → эвристики),
  эмбеддинги — `ollama`; `ML_SHOW_DEGRADED_WARNING=true`.
- Токен VK ID у сервера свой: `.vk/token.json` не копируется (refresh-токен одноразовый).

## Другой сервер

```bash
make deploy HOST=1.2.3.4 SSH_USER=ubuntu [HTTP_PORT=8080]
make vk-login HOST=1.2.3.4 SSH_USER=ubuntu   # только для токена VK ID вместо сервисного ключа
make seed URL=http://1.2.3.4
make smoke URL=http://1.2.3.4
```

## На сервере

`.env` принадлежит root, поэтому compose — через sudo:

```bash
cd /opt/mp
sudo docker compose ps
sudo docker compose logs -f --tail=100 search_service
sudo docker compose stop      # погасить стенд; обратно — sudo docker compose start
curl -s localhost:8085/health # какой провайдер моделей отвечает сейчас
```

Новый сервис со своей БД → строка `<NAME>_DB_PASSWORD=...` в `roles/env/templates/env.j2` по образцу
`SEARCH_DB_PASSWORD`.
