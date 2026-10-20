"""Записывает НАСТОЯЩИЕ ответы VK в tests/fixtures/vk/real/ — для сверки разбора с живым API.

Нужен сервисный ключ VK в окружении. Только стандартная библиотека, ставить ничего не надо:

    VK_SERVICE_TOKEN=... python scripts/record_vk_fixtures.py krsk_news "ДТП Красноярск"

Что делает: groups.getById, wall.get (первые 20 постов), newsfeed.search за последние 14 дней
(первые 20 результатов), а также названия найденных источников (groups.getById / users.get).
newsfeed.search закрыт для части ключей (ошибка 1051) — тогда поиск пропускается, остальное пишется.
Токен в файлы не попадает: пишем ответ VK и список параметров без access_token.
После записи `pytest tests/test_vk_real_fixtures.py` проверит, что разбор понимает живые ответы.
Записанные файлы — это публичные посты VK: перед коммитом просмотрите их глазами.
"""

import json
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

API = "https://api.vk.com/method/"
VERSION = os.environ.get("VK_API_VERSION", "5.199")
OUT = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "vk" / "real"
PAUSE = 0.4  # ≈3 запроса в секунду
USAGE = (
    "Использование:\n"
    '  VK_SERVICE_TOKEN=... python scripts/record_vk_fixtures.py <имя_группы> "<поисковая фраза>"'
)


class VkError(Exception):
    pass


def call(token: str, method: str, **params: str | int) -> dict[str, Any]:
    form = {k: str(v) for k, v in params.items()} | {"access_token": token, "v": VERSION}
    request = urllib.request.Request(API + method, data=urllib.parse.urlencode(form).encode())
    with urllib.request.urlopen(request, timeout=20) as response:
        payload: dict[str, Any] = json.load(response)
    time.sleep(PAUSE)
    if "error" in payload:
        error = payload["error"]
        raise VkError(f"VK {method}: ошибка {error.get('error_code')}: {error.get('error_msg')}")
    payload["_recorded"] = {
        "at": datetime.now(UTC).isoformat(timespec="seconds"),
        "method": method,
        "params": {k: v for k, v in params.items()},  # без access_token
        "v": VERSION,
    }
    return payload


def save(name: str, payload: dict[str, Any]) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        "записано:",
        (OUT / name).relative_to(Path.cwd()) if OUT.is_relative_to(Path.cwd()) else OUT / name,
    )


def main() -> None:
    token = os.environ.get("VK_SERVICE_TOKEN", "")
    if not token or len(sys.argv) < 3:
        sys.exit(USAGE)
    try:
        record(token, sys.argv[1], sys.argv[2])
    except VkError as exc:
        sys.exit(str(exc))


def record(token: str, handle: str, query: str) -> None:
    group = call(token, "groups.getById", group_id=handle, fields="city,members_count,is_closed")
    save("groups_get_by_id.json", group)
    groups = group["response"]
    groups = groups["groups"] if isinstance(groups, dict) else groups
    owner_id = -int(groups[0]["id"])

    save("wall_get.json", call(token, "wall.get", owner_id=owner_id, count=20))

    now = int(time.time())
    try:
        search = call(
            token, "newsfeed.search", q=query, count=20, start_time=now - 14 * 86400, end_time=now
        )
    except VkError as exc:
        print(f"{exc} — поиск пропущен («везде» по VK идёт через Яндекс)")
        return
    save("newsfeed_search.json", search)

    owners = {int(i["owner_id"]) for i in search["response"].get("items", []) if "owner_id" in i}
    group_ids = ",".join(str(-o) for o in sorted(owners) if o < 0)
    user_ids = ",".join(str(o) for o in sorted(owners) if o > 0)
    if group_ids:
        save("groups_cards.json", call(token, "groups.getById", group_ids=group_ids))
    if user_ids:
        save("users_get.json", call(token, "users.get", user_ids=user_ids))


if __name__ == "__main__":
    main()
