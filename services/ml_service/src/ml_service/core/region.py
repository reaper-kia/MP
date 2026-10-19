"""Привязка текста к Красноярскому краю по справочнику + «чужие» места для «той же новости»."""

from ml_service.core.text import stem, tokens

# Города, районы, узнаваемые объекты края
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
    "Ванавара",
    "Богучаны",
    "Кодинск",
    "Кежма",
    "Емельяново",
    "Березовка",
    "Ужур",
    "Иланский",
    "Заозёрный",
    "Шушенское",
    "Ермаковское",
    "Курагино",
    "Идринское",
    "Балахта",
    "Енисей",
    "Ангара",
    "Красноярская ГЭС",
    "Саяно-Шушенская ГЭС",
    "Ергаки",
    "Норникель",
    "СФУ",
    "Красмаш",
    "КрасЖД",
)
# Места вне края: пост о них — сигнал «другое событие» в сценарии «текст новости»
OTHER_PLACES = (
    "Москва",
    "Санкт-Петербург",
    "Петербург",
    "Новосибирск",
    "Омск",
    "Томск",
    "Кемерово",
    "Новокузнецк",
    "Иркутск",
    "Барнаул",
    "Абакан",
    "Кызыл",
    "Хакасия",
    "Тыва",
    "Якутск",
    "Екатеринбург",
    "Казань",
    "Нижний Новгород",
    "Самара",
    "Уфа",
    "Челябинск",
    "Тюмень",
    "Хабаровск",
    "Владивосток",
    "МКАД",
)
VOWELS = "аеёиоуыэюяьй"


ADJ_ENDINGS = ("ий", "ый", "ой", "ая", "ое", "ие", "ые", "ую")


def _key(word: str) -> str:
    """Основа для склонений: «Назарово» → «назаров», «Канск» → «канск» (→ «Канском»),
    «Красноярский» → «красноярск» (→ «Красноярском»)."""
    w = word.lower().replace("ё", "е")
    if len(w) >= 6 and w.endswith(ADJ_ENDINGS):
        return w[:-2]
    return w[:-1] if (len(w) > 4 and w[-1] in VOWELS) or (len(w) > 3 and w[-1] == "й") else w


Key = tuple[tuple[str, ...], str]


def _build_keys(names: tuple[str, ...]) -> list[Key]:
    """Ключ — основы КАЖДОГО слова названия: «Красноярская ГЭС» не путается с «Красноярска»."""
    keys: list[Key] = [(tuple(_key(t.text) for t in tokens(name)), name) for name in names]
    # многословные раньше, внутри — длинные раньше коротких
    keys.sort(key=lambda kv: (len(kv[0]), sum(map(len, kv[0]))), reverse=True)
    return keys


_KEYS = _build_keys(GAZETTEER)
_OTHER_KEYS = _build_keys(OTHER_PLACES)


def _word_matches(word: str, key: str) -> bool:
    # короткие ключи («уяр», «сфу», «гэс») — только целым словом (+ окончание), иначе ложные
    if len(key) >= 4:
        return word.startswith(key)
    return word == key or (word[:-1] == key and word[-1] in "аеиоуыюяй")


def _find_all(text: str, keys: list[Key]) -> list[str]:
    words = [t.text.lower().replace("ё", "е") for t in tokens(text)]
    found: list[str] = []
    i = 0
    while i < len(words):
        step = 1
        for parts, name in keys:
            window = words[i : i + len(parts)]
            if len(window) == len(parts) and all(map(_word_matches, window, parts)):
                if name not in found:
                    found.append(name)
                step = len(parts)
                break
        i += step
    return found


def find_region(text: str) -> str:
    """Каноничное название первого найденного упоминания края («Ачинск») или ""."""
    found = _find_all(text, _KEYS)
    return found[0] if found else ""


def find_all_regions(text: str) -> list[str]:
    return _find_all(text, _KEYS)


def find_other_places(text: str) -> list[str]:
    return _find_all(text, _OTHER_KEYS)


def places(text: str) -> set[str]:
    """Конкретные места (края и вне его) — для сравнения «то же ли место».

    «Красноярский край» не конкретное место: он совместим с любым городом края.
    """
    return (set(find_all_regions(text)) - {"Красноярский край"}) | set(find_other_places(text))


# основы региональных слов: в лексической оценке не считаются совпадением по теме
REGION_STEMS = frozenset(stem(t.text) for name in GAZETTEER for t in tokens(name)) | {
    "край",
    "крае",
    "краю",
    "края",
    "краев",
    "регион",
    "регио",
}
