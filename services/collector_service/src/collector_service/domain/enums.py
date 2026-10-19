from enum import StrEnum


class Platform(StrEnum):
    VK = "vk"
    OK = "ok"
    MAX = "max"
    NEWS = "news"


class Health(StrEnum):
    OK = "ok"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"
