"""Каталог источников из seed/sources.xlsx → POST /api/v1/sources (TL-06).

    make seed                              # http://localhost:8000, seed/sources.xlsx
    make seed URL=http://1.2.3.4           # сервер (через nginx фронта)
    python3 scripts/seed_sources.py URL [файл.xlsx] [--strict]

Файл: колонка A — ссылка, B — название (пусто — возьмём с площадки), C — региональный (да/нет,
пусто = да). Шапка в первой строке не обязательна. Только стандартная библиотека.

Имена источников берутся с площадки: на `COLLECTOR_FAKE=true` получатся тестовые имена, а строки OK
и MAX до B1-04 / B1-05 вернут 501 — скрипт покажет их в отчёте как ошибки со строкой.
"""

from __future__ import annotations

import json
import re
import sys
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree as ET

DEFAULT_FILE = Path(__file__).resolve().parent.parent / "seed" / "sources.xlsx"
TARGET_VK = 30  # DoD TL-06: в каталоге ≥ 30 источников VK

_NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
_YES = {"да", "д", "yes", "y", "true", "1", "+", ""}
_NO = {"нет", "н", "no", "n", "false", "0", "-"}


@dataclass(frozen=True)
class Row:
    number: int  # номер строки в Excel
    url: str
    name: str
    is_regional: bool | None  # None — непонятное значение в колонке C


def _column(ref: str) -> int:
    letters = re.match(r"[A-Z]+", ref)
    index = 0
    for ch in letters.group() if letters else "A":
        index = index * 26 + ord(ch) - 64
    return index - 1


def read_rows(path: Path) -> list[Row]:
    """Колонки A–C первого листа. Пустые строки и шапка (A без точки и слэша) пропускаются."""
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        shared: list[str] = []
        if "xl/sharedStrings.xml" in names:
            root = ET.fromstring(z.read("xl/sharedStrings.xml"))
            for si in root.findall("m:si", _NS):
                shared.append("".join(t.text or "" for t in si.iter(f"{{{_NS['m']}}}t")))
        sheets = sorted(n for n in names if re.fullmatch(r"xl/worksheets/sheet\d+\.xml", n))
        if not sheets:
            raise SystemExit(f"В {path} нет листов")
        sheet = ET.fromstring(z.read(sheets[0]))

    rows: list[Row] = []
    first_filled = True
    for row in sheet.iter(f"{{{_NS['m']}}}row"):
        cells = ["", "", ""]
        for c in row.findall("m:c", _NS):
            col = _column(c.get("r", "A1"))
            if col > 2:
                continue
            value = c.find("m:v", _NS)
            inline = c.find("m:is", _NS)
            if c.get("t") == "s" and value is not None and value.text:
                text = shared[int(value.text)]
            elif inline is not None:
                text = "".join(t.text or "" for t in inline.iter(f"{{{_NS['m']}}}t"))
            else:
                text = (value.text or "") if value is not None else ""
            cells[col] = text.strip()
        url, name, regional = cells
        if not (url or name or regional):
            continue
        if first_filled:
            first_filled = False
            if url and "." not in url and "/" not in url:
                continue  # шапка
        lowered = regional.lower()
        is_regional = True if lowered in _YES else False if lowered in _NO else None
        rows.append(Row(int(row.get("r", "0")), url, name, is_regional))
    return rows


def api(base: str, method: str, path: str, body: dict[str, object] | None = None):
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(
        base + path, data=data, method=method, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return response.status, json.loads(response.read() or b"null")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or b"null")
        except ValueError:
            return e.code, None


def create(base: str, body: dict[str, object]) -> tuple[int, object]:
    """POST /sources с одним повтором при таймауте: площадка могла ответить медленно, а источник —
    уже создаться (тогда повтор вернёт 409 «уже есть»)."""
    try:
        return api(base, "POST", "/api/v1/sources", body)
    except TimeoutError:
        return api(base, "POST", "/api/v1/sources", body)


def describe(status: int, payload: object) -> str:
    error = payload.get("error", {}) if isinstance(payload, dict) else {}
    code, message = error.get("code", ""), error.get("message", "")
    return f"HTTP {status} {code} {message}".strip()


def main(argv: list[str]) -> int:
    args = [a for a in argv if not a.startswith("--")]
    strict = "--strict" in argv
    base = (args[0] if args else "http://localhost:8000").rstrip("/")
    path = Path(args[1]) if len(args) > 1 else DEFAULT_FILE
    if not path.exists():
        print(f"Нет файла {path}: положи туда список источников (A — ссылка, B — название, C — да/нет)")
        return 1
    rows = read_rows(path)
    if not rows:
        print(f"В {path} нет строк с источниками — заполни seed/sources.xlsx и запусти снова")
        return 1

    print(f"Загружаю {len(rows)} строк из {path.name} в {base}")
    added = existed = 0
    errors: list[tuple[int, str, str]] = []
    for row in rows:
        if not row.url:
            errors.append((row.number, row.name, "не указана ссылка (колонка A)"))
            continue
        if row.is_regional is None:
            errors.append((row.number, row.url, "колонка C: ожидается «да» или «нет»"))
            continue
        body: dict[str, object] = {"url": row.url, "is_regional": row.is_regional}
        if row.name:
            body["name"] = row.name
        try:
            status, payload = create(base, body)
        except (urllib.error.URLError, TimeoutError) as e:
            if not (added or existed or errors):  # первая же строка — стенд не поднят
                print(f"Не достучался до {base}: {e}.")
                print("Поднят ли стенд? (README → «Быстрый старт»)")
                return 1
            # одна площадка долго отвечает (VK / OK) — не бросаем остальные строки
            errors.append((row.number, row.url, f"нет ответа ({e}) — запустите make seed ещё раз"))
            continue
        if status == 201:
            added += 1
            print(f"  + {row.number:>3}  {row.url}  →  {payload.get('name', '')}")
        elif status == 409:
            existed += 1
        else:
            errors.append((row.number, row.url, describe(status, payload)))

    print(f"\nДобавлено: {added} · уже были: {existed} · ошибки: {len(errors)}")
    for number, value, reason in errors:
        print(f"  ! строка {number}: {value} — {reason}")

    status, payload = api(base, "GET", "/api/v1/sources?platform=vk&limit=1")
    if status == 200 and isinstance(payload, dict):
        total = payload.get("total", 0)
        mark = "ок" if total >= TARGET_VK else f"нужно ≥ {TARGET_VK}"
        print(f"В каталоге VK: {total} ({mark})")
    return 1 if strict and errors else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
