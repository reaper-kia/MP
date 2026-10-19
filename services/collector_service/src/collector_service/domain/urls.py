from urllib.parse import urlsplit

from collector_service.domain.exceptions import UnsupportedUrlError


def normalize_url(raw: str) -> str:
    """'vk.com/krsk' → 'https://vk.com/krsk' (без query и якоря, без завершающего /)."""
    value = raw.strip()
    if not value:
        raise UnsupportedUrlError("Пустая ссылка")
    if "://" not in value:
        value = "https://" + value
    parts = urlsplit(value)
    if not parts.netloc:
        raise UnsupportedUrlError("Это не похоже на ссылку")
    host = parts.netloc.lower().removeprefix("www.")
    path = parts.path.rstrip("/")
    return f"https://{host}{path}"


def host_of(url: str) -> str:
    return urlsplit(normalize_url(url)).netloc


def path_parts(url: str) -> list[str]:
    return [p for p in urlsplit(normalize_url(url)).path.split("/") if p]
