# Деплой

Нужно у себя: `ansible` и `rsync` (Arch: `pacman -S ansible rsync`).
На сервере: Ubuntu 22.04+/Debian 12+, SSH-доступ пользователем с sudo.

```bash
make deploy HOST=1.2.3.4 SSH_USER=ubuntu     # из корня проекта
make smoke URL=http://1.2.3.4                # проверка снаружи
```

Без `HOST=` берётся `inventory/dev.yml`. Настройки — `playbooks/group_vars/all.yml`.

Роли по порядку:

| Роль | Что делает |
|---|---|
| `common` | проверка SSH, git/curl/rsync |
| `docker` | Docker + compose + buildx из репозиториев дистрибутива, зеркало Docker Hub |
| `sync` | rsync папки проекта в `/opt/mp` (git на сервере не нужен, незакоммиченное тоже уедет) |
| `env` | `.env` из шаблона; пароли и JWT-секрет генерируются один раз и хранятся в `infra/ansible/.secrets/` |
| `start` | `docker compose up -d --build`, ждёт `/health/ready` |

Новый сервис со своей БД → добавь строку `<NAME>_DB_PASSWORD=...` в `roles/env/templates/env.j2`
по образцу `EXAMPLE_DB_PASSWORD`.

Логи на сервере: `ssh ubuntu@1.2.3.4 'cd /opt/mp && sudo docker compose logs -f --tail=100 gateway'`.

Если ругается на `ansible.posix.synchronize`: `ansible-galaxy collection install ansible.posix`.
