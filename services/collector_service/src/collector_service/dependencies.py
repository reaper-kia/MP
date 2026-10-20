"""Composition root: настройки → клиенты площадок → коннекторы → реестр → Mediator.

Здесь и только здесь выбирается, как получаем публикации с каждой площадки:
  VK    — VK API (сервисный ключ или токен VK ID с автообновлением); «везде» — newsfeed.search,
          а если он ключу закрыт (токен пользователя) — Yandex Search site:vk.com + wall.getById;
  OK    — публичные страницы ok.ru; «везде» — Yandex Search API + открыть каждую ссылку;
  MAX   — Bot API (каналы, где бот — администратор); «везде» нет: веб без входа пуст;
  NEWS  — RSS-ленты сайтов из перечня (NEWS_SITES).
"""

import logging
from dataclasses import dataclass
from pathlib import Path

import httpx
from redis.asyncio import Redis

from collector_service.applications.behaviors import CachingBehavior, LoggingBehavior
from collector_service.applications.handlers.platforms import (
    GetPlatformsQueryHandler,
    SearchPlatformQueryHandler,
)
from collector_service.applications.handlers.sources import (
    CollectFromSourceQueryHandler,
    ResolveSourceQueryHandler,
)
from collector_service.applications.limits import CollectLimits
from collector_service.applications.mediator import Mediator
from collector_service.applications.ports.cache import Cache
from collector_service.applications.ports.connectors import ConnectorRegistry, PlatformConnector
from collector_service.applications.queries.platforms import GetPlatformsQuery, SearchPlatformQuery
from collector_service.applications.queries.sources import (
    CollectFromSourceQuery,
    ResolveSourceQuery,
)
from collector_service.domain.enums import Platform
from collector_service.infra.cache import TtlCache
from collector_service.infra.config import Settings
from collector_service.infra.connectors.fake import FakeConnector
from collector_service.infra.connectors.max import MaxConnector
from collector_service.infra.connectors.news import NewsConnector
from collector_service.infra.connectors.ok import OkConnector
from collector_service.infra.connectors.registry import InMemoryConnectorRegistry
from collector_service.infra.connectors.site_search import (
    SiteSearch,
    WithSearchFallback,
    WithSiteSearch,
)
from collector_service.infra.connectors.vk import VkConnector
from collector_service.infra.http import HttpxFormPoster, HttpxJsonPoster, create_http_client
from collector_service.infra.max_api.client import MaxApiClient
from collector_service.infra.news.sites import parse_sites
from collector_service.infra.redis_cache import RedisCache
from collector_service.infra.vk_api.client import VkApiClient
from collector_service.infra.vk_api.limiter import RateLimiter
from collector_service.infra.vk_api.tokens import StaticToken, TokenSource, VkIdToken
from collector_service.infra.web.fetcher import HostLimiters, HttpxWebFetcher, WebFetcher
from collector_service.infra.yandex_search.client import YandexSearchClient

RESOLVE_CACHE_TTL = 600.0

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Container:
    http: httpx.AsyncClient
    mediator: Mediator
    redis: Redis | None = None

    async def close(self) -> None:
        await self.http.aclose()
        if self.redis is not None:
            await self.redis.aclose()


def build_vk_tokens(settings: Settings, http: httpx.AsyncClient) -> TokenSource:
    """Файл токена VK ID (scripts/vk_token.py) главнее VK_SERVICE_TOKEN: он сам обновляется."""
    path = Path(settings.vk_token_file) if settings.vk_token_file else None
    if path is not None and path.is_file():
        tokens = VkIdToken(HttpxFormPoster(http), path, settings.vk_id_client_id)
        if tokens.configured:
            logger.info("VK: токен VK ID из %s (автообновление)", path)
            return tokens
    return StaticToken(settings.vk_service_token)


def build_vk(settings: Settings, http: httpx.AsyncClient) -> VkConnector:
    client = VkApiClient(
        HttpxFormPoster(http),
        tokens=build_vk_tokens(settings, http),
        version=settings.vk_api_version,
        limiter=RateLimiter(settings.vk_requests_per_second),
    )
    return VkConnector(client)


def build_web_fetcher(settings: Settings, http: httpx.AsyncClient) -> WebFetcher:
    limiters = HostLimiters(
        settings.web_requests_per_second,
        {"ok.ru": settings.ok_requests_per_second},
    )
    headers = {
        "User-Agent": settings.web_user_agent,
        "Accept-Language": "ru-RU,ru;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    return HttpxWebFetcher(http, limiters, default_headers=headers)


def build_yandex(settings: Settings, http: httpx.AsyncClient) -> YandexSearchClient:
    return YandexSearchClient(
        HttpxJsonPoster(http),
        folder_id=settings.yc_folder_id,
        api_key=settings.yc_search_api_key,
        region=settings.yandex_search_region,
    )


def build_connectors(settings: Settings, http: httpx.AsyncClient) -> list[PlatformConnector]:
    if settings.collector_fake:
        return [FakeConnector(p) for p in Platform]
    web = build_web_fetcher(settings, http)
    yandex = build_yandex(settings, http)
    ok = OkConnector(web, health_url=settings.ok_health_url)
    max_api = MaxApiClient(
        http,
        token=settings.max_bot_token,
        base_url=settings.max_api_url,
        limiter=RateLimiter(settings.max_requests_per_second),
    )
    vk = build_vk(settings, http)
    return [
        WithSearchFallback(
            vk, SiteSearch(yandex, "vk.com", vk), native=settings.vk_newsfeed_search
        ),
        WithSiteSearch(ok, SiteSearch(yandex, "ok.ru", ok)),
        MaxConnector(max_api),
        NewsConnector(
            parse_sites(settings.news_sites), web, open_articles=settings.news_open_articles
        ),
    ]


def build_mediator(
    registry: ConnectorRegistry,
    limits: CollectLimits,
    cache: Cache | None = None,
    resolve_cache_ttl: float = RESOLVE_CACHE_TTL,
    collect_cache_ttl: float = 0.0,
) -> Mediator:
    """collect_cache_ttl — сколько живут посты источника и поиск по площадке (B2-20);
    0 — не кэшируем (так было до Redis и так в тестах)."""
    # снаружи внутрь: лог видит и попадания в кэш, и время реального запроса к площадке
    caching = CachingBehavior(
        cache if cache is not None else TtlCache(),
        resolve_cache_ttl,
        ttl_by_type={
            CollectFromSourceQuery: collect_cache_ttl,
            SearchPlatformQuery: collect_cache_ttl,
        },
    )
    mediator = Mediator(behaviors=[LoggingBehavior(), caching])
    mediator.register(GetPlatformsQuery, GetPlatformsQueryHandler(registry))
    mediator.register(ResolveSourceQuery, ResolveSourceQueryHandler(registry))
    mediator.register(CollectFromSourceQuery, CollectFromSourceQueryHandler(registry, limits))
    mediator.register(SearchPlatformQuery, SearchPlatformQueryHandler(registry, limits))
    return mediator


def build_cache(settings: Settings) -> tuple[Cache, Redis | None]:
    """CACHE_ENABLED=true — Redis (переживает перезапуск, общий для поисков); false — карточки
    источников в памяти процесса, как до B2-20."""
    if not settings.cache_enabled:
        logger.info("кэш выключен (CACHE_ENABLED=false): сбор не кэшируется")
        return TtlCache(), None
    client = Redis.from_url(
        settings.redis_url,
        socket_timeout=settings.redis_timeout_seconds,
        socket_connect_timeout=settings.redis_timeout_seconds,
    )
    logger.info(
        "кэш: Redis, посты %.0f с, карточки %.0f с",
        settings.cache_collect_ttl_seconds,
        settings.cache_resolve_ttl_seconds,
    )
    return RedisCache(client, settings.redis_timeout_seconds), client


def build_container(settings: Settings) -> Container:
    http = create_http_client(settings)
    registry = InMemoryConnectorRegistry(build_connectors(settings, http))
    limits = CollectLimits(
        per_source=settings.default_max_posts_source,
        per_search=settings.default_max_posts_search,
        budget_seconds=settings.collect_budget_seconds,
    )
    cache, redis = build_cache(settings)
    mediator = build_mediator(
        registry,
        limits,
        cache,
        resolve_cache_ttl=settings.cache_resolve_ttl_seconds,
        collect_cache_ttl=settings.cache_collect_ttl_seconds if settings.cache_enabled else 0.0,
    )
    return Container(http=http, mediator=mediator, redis=redis)
