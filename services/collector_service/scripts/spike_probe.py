"""B1-01: смотрит, что публичная страница отдаёт обычному клиенту без логина.

Только стандартная библиотека. Запускать с компьютера, у которого есть доступ к ok.ru / max.ru:

    python scripts/spike_probe.py https://ok.ru/group/<id>/topics https://m.ok.ru/group/<id>/topics
    python scripts/spike_probe.py --save https://max.ru/<канал>

Для каждой ссылки печатает статус, итоговый адрес, размер, признаки анти-бота и признаки того, что
в странице есть сами посты (теги <time>, JSON внутри HTML, русский текст). С --save кладёт ответ в
tests/fixtures/spike/ — оттуда берутся реальные примеры для парсера и для docs/collector-spike.md.
Запросы идут по одному с паузой 1.5 с, без повторов: это проба, а не сбор.
"""

import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "spike"
UA = "Mozilla/5.0 (X11; Linux x86_64) MP-mediamonitoring/0.1 (spike)"
ANTIBOT = (
    "captcha",
    "капча",
    "подтвердите, что вы не робот",
    "доступ ограничен",
    "too many requests",
)
EMBEDDED_JSON = (
    "__NEXT_DATA__",
    "__data.json",
    "window.__",
    "application/ld+json",
    "__INITIAL_STATE__",
)


def probe(url: str, save: bool) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "ru-RU,ru"})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            status, final_url, headers = response.status, response.geturl(), response.headers
            body = response.read()
    except urllib.error.HTTPError as exc:
        status, final_url, headers, body = exc.code, url, exc.headers, exc.read()
    except OSError as exc:
        print(f"{url}\n  сеть: {type(exc).__name__}: {exc}\n")
        return
    text = body.decode("utf-8", errors="replace")
    lower = text.lower()
    visible = re.sub(r"<[^>]+>", " ", text)
    antibot = [m for m in ANTIBOT if m in lower] or "нет"
    embedded = [m for m in EMBEDDED_JSON if m in text] or "нет"
    print(url)
    print(f"  статус: {status}   итоговый адрес: {final_url}")
    print(f"  тип: {headers.get('content-type')}   размер: {len(body)} байт")
    print(f"  Retry-After: {headers.get('retry-after')}")
    print(f"  признаки анти-бота: {antibot}")
    print(f"  тегов <time>: {lower.count('<time')}   <article>: {lower.count('<article')}")
    print(f"  JSON внутри HTML: {embedded}")
    print(f"  русских слов в тексте: {len(re.findall(r'[А-Яа-яЁё]{4,}', visible))}")
    if save:
        OUT.mkdir(parents=True, exist_ok=True)
        path = OUT / (
            re.sub(r"[^A-Za-z0-9]+", "_", final_url.split("://")[-1]).strip("_")[:80] + ".html"
        )
        path.write_bytes(body)
        print(f"  сохранено: {path}")
    print()


def main() -> None:
    args = sys.argv[1:]
    save = "--save" in args
    urls = [a for a in args if a != "--save"]
    if not urls:
        sys.exit(__doc__)
    for i, url in enumerate(urls):
        if i:
            time.sleep(1.5)
        probe(url, save)


if __name__ == "__main__":
    main()
