# auth_service

Пользователи, пароли (argon2), JWT access-токены (HS256) и refresh-сессии с ротацией.

gRPC: `contracts/auth/v1/auth_service.proto` — Register, Login, Refresh, Logout, GetUser. Порт 50051.

Локально: `make db` (из корня), затем `cp .env.example .env && uv sync && uv run alembic upgrade head && uv run auth-service`.
