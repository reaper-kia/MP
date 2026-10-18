# Деплой на сервер по IP

Нужно на своей машине: `ansible` (на Arch: `pacman -S ansible`, там уже есть `ansible.posix` и `community.general`), `rsync`.
На сервере: Ubuntu 22.04+/Debian 12+, SSH-доступ пользователем с sudo.

```bash
# 1. Один раз на новый сервер — Docker, зеркала Docker Hub, firewall
make server-setup HOST=1.2.3.4 SSH_USER=ubuntu

# 2. Выкатить (и каждый следующий раз — то же самое)
make deploy HOST=1.2.3.4 SSH_USER=ubuntu
make deploy HOST=1.2.3.4 SSH_USER=ubuntu KAFKA=true   # с Kafka

# Проверка снаружи
make smoke URL=http://1.2.3.4
```

Без `HOST=` используется `inventory.ini` (впиши туда IP). Настройки (порт, Kafka, админы, зеркала) — `playbooks/group_vars/all.yml`. Развернуть на этой же машине —
раскомментируй `local ansible_connection=local`.

Что происходит при deploy:
1. rsync текущей рабочей папки в `/opt/mp` (git не нужен, незакоммиченное тоже уедет);
2. `.env` рендерится из `playbooks/group_vars/all.yml`, пароли/секреты генерируются один раз и лежат локально в `.secrets/` (не в git);
3. `docker compose up -d --build`;
4. ждём `/health/ready` через nginx.

Наружу открыт только `http_port` (80): nginx фронта отдаёт SPA и проксирует `/api`, `/ws`, `/docs` в gateway.
Postgres/Redis/gRPC-порты привязаны к 127.0.0.1 сервера.

Посмотреть логи на сервере: `ssh ubuntu@1.2.3.4 'cd /opt/mp && docker compose logs -f --tail=100 gateway'`.

Если `ansible.posix` нет: `ansible-galaxy collection install ansible.posix community.general`.
