from functools import lru_cache

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Красноярские новостные сайты. Ленты открылись при пробе 2026-10-19 (docs/collector-spike.md §6);
# gornovosti.ru, prmira.ru, krsk.kp.ru, dela.ru, 7kanal.com, tvk6.ru — лента не открылась
DEFAULT_NEWS_SITES = (
    "ngs24.ru|https://ngs24.ru/rss-feeds/rss.xml|НГС24;"
    "newslab.ru|https://newslab.ru/news/all/rss|Newslab.ru;"
    "krsk.aif.ru|https://krsk.aif.ru/rss/all.php|АиФ-Красноярск;"
    "sibnovosti.ru|https://sibnovosti.ru/rss/|Сибирское агентство новостей"
)


class Settings(BaseSettings):
    grpc_address: str = "[::]:50054"

    # true — все площадки отдают тестовые посты [FAKE]. На демо — ВСЕГДА false.
    collector_fake: bool = False

    # VK API (B1-03)
    vk_service_token: str = ""
    # Токен VK ID с автообновлением (scripts/vk_token.py пишет .vk/token.json). Если файл есть —
    # он главнее VK_SERVICE_TOKEN. В compose: VK_TOKEN_FILE=/vk/token.json (том ./.vk:/vk)
    vk_token_file: str = ""
    vk_id_client_id: str = "54832790"
    vk_api_version: str = "5.199"
    vk_requests_per_second: float = 3.0
    # Свой поиск VK по всей площадке (newsfeed.search). VK закрыл его и сервисному ключу, и токену
    # VK ID (ошибка 1051), поэтому по умолчанию не пробуем: «везде» во VK — источники каталога
    # (и Яндекс site:vk.com, если задан YC_SEARCH_API_KEY)
    vk_newsfeed_search: bool = False

    # Yandex Search API — глобальный поиск по OK / MAX / сайтам (B1-06)
    yc_folder_id: str = ""
    yc_search_api_key: str = ""

    # MAX Bot API (B1-05): токен бота с business.max.ru; бот — администратор нужных каналов
    max_bot_token: str = ""
    max_api_url: str = "https://platform-api2.max.ru"

    # OK (B1-04): страница, по которой проверяем, что ok.ru отдаёт группы без логина
    ok_health_url: str = "https://ok.ru/ngs24"

    # Yandex Search API: регион выдачи (62 — Красноярск), чтобы региональное было выше
    yandex_search_region: int = 62

    # HTTP к площадкам
    http_timeout_seconds: float = 15.0
    http_user_agent: str = "Mozilla/5.0 (X11; Linux x86_64) MP-mediamonitoring/0.1"
    # Доп. корневые сертификаты (PEM), например УЦ Минцифры для MAX: добавляются к certifi
    http_ca_bundle: str = ""
    # Публичные страницы (OK, MAX, сайты) отдают ленту только «обычному браузеру»
    web_user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"
    )
    # Не чаще N запросов в секунду на один хост (B1-09 п. 3)
    web_requests_per_second: float = 1.0
    ok_requests_per_second: float = 0.5
    max_requests_per_second: float = 2.0

    # Новостные сайты (B1-08): "хост|адрес RSS|Название; ..." — см. infra/news/sites.py
    news_sites: str = DEFAULT_NEWS_SITES
    # true — если в ленте только анонс, открываем статью и берём текст со страницы
    news_open_articles: bool = True

    # Лимиты по умолчанию, если в запросе max_posts = 0
    default_max_posts_source: int = 300
    default_max_posts_search: int = 500

    # Бюджет на один сбор: search_service ждёт цель 60 с — отдаём, что успели, раньше (B1-09)
    collect_budget_seconds: float = 50.0
    # Кэш в Redis (B2-20): посты источника / поиск по площадке и карточка источника по ссылке.
    # CACHE_ENABLED=false — как до B2-20: сбор не кэшируется, карточка — в памяти процесса
    cache_enabled: bool = True
    redis_url: str = "redis://localhost:6379/0"
    redis_timeout_seconds: float = 0.2
    cache_collect_ttl_seconds: float = 600.0
    # Кэш ResolveSource (B1-09): одна и та же ссылка — один запрос к площадке за 10 минут.
    # Старое имя RESOLVE_CACHE_TTL_SECONDS тоже понимаем
    cache_resolve_ttl_seconds: float = Field(
        default=600.0,
        validation_alias=AliasChoices("cache_resolve_ttl_seconds", "resolve_cache_ttl_seconds"),
    )

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
