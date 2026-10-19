"""Привязка текста к Красноярскому краю по справочнику. Дополнять в ML-04."""

from ml_service.core.text import tokens

# Города, районы, узнаваемые объекты края (начальный список — расширить)
GAZETTEER = (
    "Красноярский край",
    "Красноярск",
    "Норильск",
    "Ачинск",
    "Канск",
    "Минусинск",
    "Железногорск",
    "Зеленогорск",
    "Лесосибирск",
    "Назарово",
    "Шарыпово",
    "Дивногорск",
    "Сосновоборск",
    "Боготол",
    "Бородино",
    "Енисейск",
    "Уяр",
    "Игарка",
    "Дудинка",
    "Таймыр",
    "Эвенкия",
    "Емельяново",
    "Березовка",
    "Ужур",
    "Енисей",
    "Красноярская ГЭС",
)
VOWELS = "аеёиоуыэюяь"


def _key(word: str) -> str:
    """Основа для склонений: «Назарово» → «назаров», «Канск» → «канск» (→ «Канском»)."""
    w = word.lower().replace("ё", "е")
    return w[:-1] if len(w) > 4 and w[-1] in VOWELS else w


# по первому слову названия: «Красноярская ГЭС» ловится по «красноярск…» вместе с городом
_KEYS: list[tuple[str, str]] = []
for _name in GAZETTEER:
    _first = next(tokens(_name), None)
    if _first is not None and all(_key(_first.text) != k for k, _ in _KEYS):
        _KEYS.append((_key(_first.text), _name))
_KEYS.sort(key=lambda kv: len(kv[0]), reverse=True)  # длинные ключи раньше коротких


def find_region(text: str) -> str:
    """Каноничное название первого найденного упоминания края («Ачинск») или ""."""
    for token in tokens(text):
        word = token.text.lower().replace("ё", "е")
        for key, name in _KEYS:
            if word.startswith(key):
                return name
    return ""
