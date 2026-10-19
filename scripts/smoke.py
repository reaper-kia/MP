"""Сквозная проверка поднятого стенда через Gateway — путь пользователя из ТЗ.

make smoke                         # http://localhost:8000
make smoke URL=http://1.2.3.4      # сервер после деплоя (через nginx фронта)

Пока сценарий не реализован, ручка отвечает 501 NOT_IMPLEMENTED — smoke так и напишет.
"""

import io
import re
import sys
import time
import uuid
import zipfile
from datetime import date, timedelta
from xml.etree import ElementTree as ET

import httpx

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000").rstrip("/")
FINAL = {"completed", "partial", "failed", "cancelled"}
SEARCH_TIMEOUT_SECONDS = 180


_NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


def xlsx_publication_rows(content: bytes) -> list[int]:
    """По каждому листу XLSX: сколько строк с прямой ссылкой (http…) на публикацию.

    Только stdlib (в gateway нет openpyxl). Ссылкой считаем текст ячейки, начинающийся с http,
    либо гиперссылку листа — строка с заголовком таблицы не считается.
    """
    counts: list[int] = []
    with zipfile.ZipFile(io.BytesIO(content)) as z:
        shared: list[str] = []
        if "xl/sharedStrings.xml" in z.namelist():
            root = ET.fromstring(z.read("xl/sharedStrings.xml"))
            for si in root.findall("m:si", _NS):
                shared.append("".join(t.text or "" for t in si.iter(f"{{{_NS['m']}}}t")))
        sheets = sorted(n for n in z.namelist() if re.fullmatch(r"xl/worksheets/sheet\d+\.xml", n))
        for name in sheets:
            root = ET.fromstring(z.read(name))
            rows_with_url = 0
            for row in root.iter(f"{{{_NS['m']}}}row"):
                has_url = False
                for c in row.findall("m:c", _NS):
                    v = c.find("m:v", _NS)
                    is_ = c.find("m:is", _NS)
                    if c.get("t") == "s" and v is not None and v.text:
                        text = shared[int(v.text)]
                    elif is_ is not None:
                        text = "".join(t.text or "" for t in is_.iter(f"{{{_NS['m']}}}t"))
                    else:
                        text = (v.text or "") if v is not None else ""
                    if text.startswith(("http://", "https://")):
                        has_url = True
                        break
                rows_with_url += has_url
            links = len(list(root.iter(f"{{{_NS['m']}}}hyperlink")))
            counts.append(max(rows_with_url, links))
    return counts


def check(cond: bool, what: str, r: httpx.Response | None = None) -> None:
    print(("  ok   " if cond else "  FAIL ") + what)
    if cond:
        return
    if r is not None:
        try:
            error = r.json().get("error", {})
        except ValueError:
            error = {}
        if error.get("code") == "NOT_IMPLEMENTED":
            print(f"       → ещё не реализовано: {error.get('message')}")
        else:
            print(f"       → HTTP {r.status_code}: {r.text[:300]}")
    raise SystemExit(1)


def main() -> None:
    print(f"Smoke test against {BASE}")
    with httpx.Client(base_url=BASE, timeout=30) as c:
        ready = c.get("/health/ready").json()
        print(f"  ready: {ready}")
        check(ready.get("status") == "ok", "все сервисы отвечают")

        r = c.get("/api/v1/platforms")
        check(r.status_code == 200 and len(r.json()) >= 3, "площадки", r)
        fake = any("ТЕСТОВЫЕ" in (p.get("note") or "") for p in r.json())
        print(
            f"  collector: {'ТЕСТОВЫЕ данные (COLLECTOR_FAKE=true)' if fake else 'реальные площадки'}"
        )

        r = c.post("/api/v1/query/analyze", json={"query": "Безопасность дорожного движения"})
        check(r.status_code == 200 and r.json()["search_queries"], "разбор запроса", r)

        handle = f"smoke_{uuid.uuid4().hex[:6]}" if fake else "krsk_news"
        r = c.post("/api/v1/sources/resolve", json={"url": f"vk.com/{handle}"})
        check(r.status_code == 200, "предпросмотр источника", r)
        r = c.post("/api/v1/sources", json={"url": f"vk.com/{handle}", "is_regional": True})
        check(r.status_code in (201, 409), "добавить источник (или уже есть)", r)
        r = c.get("/api/v1/sources?platform=vk&limit=200")
        check(r.status_code == 200 and r.json()["total"] >= 1, "список источников", r)
        source_ids = [s["id"] for s in r.json()["items"]][:5]

        today = date.today()
        body = {
            "query": "Безопасность дорожного движения в Красноярском крае",
            "period_from": (today - timedelta(days=6)).isoformat(),
            "period_to": today.isoformat(),
            "mode": "selected",
            "platforms": ["vk"],
            "source_ids": source_ids,
        }
        r = c.post("/api/v1/searches", json=body)
        check(r.status_code == 202 and r.json()["status"] == "queued", "запуск поиска", r)
        search_id = r.json()["id"]

        started = time.monotonic()
        while True:
            r = c.get(f"/api/v1/searches/{search_id}")
            check(r.status_code == 200, "статус поиска", r)
            search = r.json()
            if search["status"] in FINAL:
                break
            if time.monotonic() - started > SEARCH_TIMEOUT_SECONDS:
                check(False, f"поиск не завершился за {SEARCH_TIMEOUT_SECONDS} с")
            time.sleep(1.5)
        elapsed = time.monotonic() - started
        check(
            search["status"] in ("completed", "partial"),
            f"поиск: {search['status']} за {elapsed:.0f} с",
        )
        total = search["counts"]["total"]
        warnings = search.get("warnings") or []
        simplified = any("упрощённом" in w or "ML_MODE=stub" in w for w in warnings)
        print(
            f"  ML: {'эвристики (упрощённый режим)' if simplified else 'модели'}; "
            f"предупреждения: {warnings or 'нет'}"
        )
        if search["counts"]:
            counts = search["counts"]
            print(
                f"  отбор: прямых {counts['direct']}, косвенных {counts['indirect']}, "
                f"спорных {counts['disputed']}, отсеяно {counts['rejected']}, "
                f"групп {counts['groups']}"
            )

        r = c.get(f"/api/v1/searches/{search_id}/results?limit=200")
        check(
            r.status_code == 200 and r.json()["total"] == total,
            f"подборка: {total} публикаций",
            r,
        )
        urls = [i["url"] for i in r.json()["items"]]
        check(len(urls) == len(set(urls)), "нет повторов одной публикации", r)

        r = c.get(f"/api/v1/searches/{search_id}/groups")
        check(r.status_code == 200, "группы", r)

        r = c.get(f"/api/v1/searches/{search_id}/export?format=xlsx")
        check(r.status_code == 200 and r.content[:2] == b"PK", "выгрузка XLSX", r)
        try:
            per_sheet = xlsx_publication_rows(r.content)
        except (zipfile.BadZipFile, ET.ParseError, KeyError, IndexError) as exc:
            check(False, f"XLSX открывается как книга Excel ({exc})")
        check(bool(per_sheet), "в XLSX есть листы")
        check(
            total in per_sheet,
            f"в XLSX {total} строк с ссылками = counts.total (по листам: {per_sheet})",
        )

        r = c.get(f"/api/v1/searches/{uuid.uuid4()}")
        check(
            r.status_code == 404 and r.json()["error"]["code"] == "SEARCH_NOT_FOUND",
            "404 SEARCH_NOT_FOUND",
            r,
        )
    print("All good")


if __name__ == "__main__":
    main()
