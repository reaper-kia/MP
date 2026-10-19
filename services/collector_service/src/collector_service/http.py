import httpx

from collector_service.config import Settings


def create_http_client(settings: Settings) -> httpx.AsyncClient:
    """Один клиент на сервис: пул соединений, таймауты, User-Agent.

    Закрывается в Container.close().
    """
    return httpx.AsyncClient(
        timeout=httpx.Timeout(settings.http_timeout_seconds),
        headers={"User-Agent": settings.http_user_agent},
        follow_redirects=True,
    )
