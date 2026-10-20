"""Записывает НАСТОЯЩИЕ страницы групп OK в tests/fixtures/ok/real/<gid>/ — для сверки разбора.

Аналог scripts/record_vk_fixtures.py (B1-12). Ключей не нужно — OK отдаёт публичные страницы групп
без входа. Только стандартная библиотека:

    python scripts/record_ok_fixtures.py                          # 3 группы OK из seed
    python scripts/record_ok_fixtures.py ok.ru/gornovosti ok.ru/group/57451052466232

На каждую группу: страница группы, лента топиков, страницы 3 первых топиков (gzip) и meta.json
с моментом загрузки в UTC — от него разбор считает «сегодня» / «вчера» на страницах.
После записи `pytest tests/test_ok_real_fixtures.py` сверит: ссылка ведёт на топик, текст из ленты
совпадает с текстом на странице топика, дата в ленте = дате на странице (обе — московское время).
Записанное — публичные посты: перед коммитом посмотрите размер и содержимое.
"""

import gzip
import json
import re
import sys
import time
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "ok" / "real"
DEFAULT_GROUPS = ["ok.ru/gornovosti", "ok.ru/delakrasnoyarsk", "ok.ru/group/57451052466232"]
TOPICS_PER_GROUP = 3
PAUSE = 2.0  # как в сервисе: OK — не чаще 0.5 запроса в секунду
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ru-RU,ru;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}
CANONICAL_GID = re.compile(r"https://ok\.ru/group/(\d+)")
TOPIC_ID = re.compile(r"topicId,(\d+)")


def get(url: str) -> str:
    request = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(request, timeout=20) as response:
        body: bytes = response.read()
        charset = response.headers.get_content_charset() or "utf-8"
    time.sleep(PAUSE)
    return body.decode(charset, errors="replace")


def save(folder: Path, name: str, html: str) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{name}.html.gz").write_bytes(gzip.compress(html.encode("utf-8")))


def record(group: str) -> None:
    url = group if group.startswith("http") else f"https://{group}"
    recorded_at = datetime.now(UTC)
    group_page = get(url)
    match = CANONICAL_GID.search(group_page)
    if match is None:
        print(f"{group}: на странице нет id группы — закрыта, удалена или анти-бот; пропускаю")
        return
    gid = match.group(1)
    folder = OUT / gid
    topics_page = get(f"https://ok.ru/group/{gid}/topics")
    tids = list(dict.fromkeys(TOPIC_ID.findall(topics_page)))[:TOPICS_PER_GROUP]
    save(folder, "group", group_page)
    save(folder, "topics", topics_page)
    for tid in tids:
        save(folder, f"topic_{tid}", get(f"https://ok.ru/group/{gid}/topic/{tid}"))
    meta = {
        "recorded_at": recorded_at.isoformat(timespec="seconds"),
        "source": url,
        "gid": gid,
        "topics": tids,
    }
    (folder / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"{group}: группа {gid}, топиков {len(tids)} → {folder}")


def main() -> None:
    for group in sys.argv[1:] or DEFAULT_GROUPS:
        try:
            record(group)
        except OSError as exc:  # сеть, 403/404 от OK
            print(f"{group}: не записано ({exc})")


if __name__ == "__main__":
    main()
