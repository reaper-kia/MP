# Деплой

Нужно у себя: `ansible` и `rsync` (Arch: `pacman -S ansible rsync`).
На сервере: Ubuntu 22.04+/Debian 12+, SSH-доступ пользователем с sudo.

```bash
make deploy HOST=1.2.3.4 SSH_USER=ubuntu     # из корня проекта
make vk-login HOST=1.2.3.4 SSH_USER=ubuntu   # один раз: вход VK ID для сервера (ссылка → адрес)
make seed URL=http://1.2.3.4                 # каталог источников из seed/sources.xlsx
make smoke URL=http://1.2.3.4                # проверка снаружи
```

Токен VK ID у сервера свой: `.vk/token.json` в rsync не уезжает. Refresh-токен одноразовый — если
локальный стенд и сервер обновляли бы один и тот же, первый же обновивший выкинул бы второго.

Без `HOST=` берётся `inventory/dev.yml`. Настройки — `playbooks/group_vars/all.yml`.

Роли по порядку:

| Роль | Что делает |
|---|---|
| `common` | проверка SSH, git/curl/rsync |
| `docker` | Docker + compose + buildx из репозиториев дистрибутива, зеркало Docker Hub |
| `sync` | rsync папки проекта в `/opt/mp` (git на сервере не нужен, незакоммиченное тоже уедет) |
| `env` | `.env` из шаблона; пароль БД генерируется один раз и хранится в `infra/ansible/.secrets/`, ключи API — из окружения машины деплоя |
| `start` | `docker compose up -d --build`, ждёт `/health/ready` |

Ключи API передаются из окружения при деплое (в git их нет):

```bash
VK_SERVICE_TOKEN=... YC_FOLDER_ID=... YC_API_KEY=... YC_SEARCH_API_KEY=... LLM_PROVIDER=yandex \
  make deploy HOST=1.2.3.4 SSH_USER=ubuntu
```

На сервере всегда `COLLECTOR_FAKE=false` (`group_vars/all.yml`). Новый сервис со своей БД → строка
`<NAME>_DB_PASSWORD=...` в `roles/env/templates/env.j2` по образцу `SEARCH_DB_PASSWORD`.

Логи на сервере: `ssh ubuntu@1.2.3.4 'cd /opt/mp && sudo docker compose logs -f --tail=100 gateway'`.

Если ругается на `ansible.posix.synchronize`: `ansible-galaxy collection install ansible.posix`.
