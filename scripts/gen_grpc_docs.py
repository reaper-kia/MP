"""contracts/**/*.proto -> docs/GRPC.md (сервисы, RPC, сообщения, enum'ы с комментариями)"""

import pathlib
import re
import sys

root = (
    pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else pathlib.Path(__file__).resolve().parents[1]
)
SCALAR = {
    "string": "string (str)",
    "bool": "bool",
    "bytes": "bytes",
    "int32": "int32",
    "int64": "int64 (int)",
    "uint32": "uint32 (int ≥ 0)",
    "uint64": "uint64",
    "float": "float",
    "double": "double",
}
order = [
    "common/v1/common.proto",
    "common/v1/platform.proto",
    "collector/v1/collector_service.proto",
    "ml/v1/ml_service.proto",
    "search/v1/search_service.proto",
]
files = [root / "contracts" / o for o in order if (root / "contracts" / o).exists()]
files += [p for p in sorted((root / "contracts").rglob("*.proto")) if p not in files]


def parse(text):
    lines = text.splitlines()
    pkg = re.search(r"^package\s+([\w.]+);", text, re.M).group(1)
    items = []  # (kind, name, comment, body_entries)
    i = 0
    pending = []
    while i < len(lines):
        ln = lines[i].strip()
        if ln.startswith("//"):
            pending.append(ln[2:].strip())
            i += 1
            continue
        m = re.match(r"(service|message|enum)\s+(\w+)\s*\{(.*)$", ln)
        if m:
            kind, name, rest = m.groups()
            comment = " ".join(pending)
            pending = []
            entries = []
            fc = []
            if rest.strip().startswith("}"):
                items.append((kind, name, comment, entries))
                i += 1
                continue
            i += 1
            while i < len(lines) and lines[i].strip() != "}":
                line = lines[i].strip()
                if line.startswith("//"):
                    fc.append(line[2:].strip())
                elif line:
                    code, _, inline = line.partition("//")
                    c = " ".join(fc + ([inline.strip()] if inline.strip() else []))
                    fc = []
                    entries.append((code.strip(), c))
                i += 1
            items.append((kind, name, comment, entries))
        else:
            if ln and not ln.startswith("//"):
                pending = []
        i += 1
    return pkg, items


def type_md(t, pkg):
    if t in SCALAR:
        return SCALAR[t]
    if t == "google.protobuf.Timestamp":
        return "Timestamp"
    full = t if "." in t else f"{pkg}.{t}"
    return f"[`{t}`](#{full.replace('.', '').lower()})"


out = [
    "# gRPC-контракты — справочник (сгенерирован из `contracts/**/*.proto`)\n",
    "> Не править руками. Источник правды — `.proto`; после изменения: `make proto` (перегенерирует и этот файл).\n",
    "Соглашения шаблона: первое поле каждого запроса — `common.v1.RequestContext context`; ошибки — gRPC status + "
    '`error-code` в trailing metadata (README §10); `optional` — поле может отсутствовать (в Python: `msg.HasField("x")`); '
    "`repeated` — список; enum с нулевым `*_UNSPECIFIED` = «не задано». Timestamp — `google.protobuf.Timestamp` (UTC).\n",
    "## Содержание\n",
]
toc = []
body = []
for f in files:
    pkg, items = parse(f.read_text())
    rel = f.relative_to(root).as_posix()
    body.append(f"# Пакет `{pkg}` — `{rel}`\n")
    toc.append(
        f"- `{pkg}` (`{rel}`): "
        + ", ".join(
            f"[{n}](#{(pkg + '.' + n).replace('.', '').lower()})"
            for k, n, _, _ in items
            if k == "service"
        )
    )
    for kind, name, comment, entries in items:
        anchor = (pkg + "." + name).replace(".", "").lower()
        body.append(f'<a id="{anchor}"></a>\n### {kind} `{pkg}.{name}`\n')
        if comment:
            body.append(comment + "\n")
        if kind == "service":
            body.append("| RPC | Запрос → ответ | Описание |\n|---|---|---|")
            for code, c in entries:
                m = re.match(r"rpc\s+(\w+)\((\w+)\)\s+returns\s+\((\w+)\)", code)
                if m:
                    body.append(f"| `{m[1]}` | {type_md(m[2], pkg)} → {type_md(m[3], pkg)} | {c} |")
        elif kind == "enum":
            body.append("| Значение | № | Описание |\n|---|---|---|")
            for code, c in entries:
                m = re.match(r"(\w+)\s*=\s*(\d+);", code)
                if m:
                    body.append(f"| `{m[1]}` | {m[2]} | {c} |")
        else:
            if not entries:
                body.append("_Пустое сообщение._")
            else:
                body.append("| № | Поле | Тип | Метка | Описание |\n|---|---|---|---|---|")
                for code, c in entries:
                    m = re.match(
                        r"(?:(repeated|optional)\s+)?([\w.]+)\s+(\w+)\s*=\s*(\d+);",
                        code,
                    )
                    if m:
                        body.append(
                            f"| {m[4]} | `{m[3]}` | {type_md(m[2], pkg)} | {m[1] or ''} | {c.replace('|', '/')} |"
                        )
        body.append("")
out += toc + [""] + body
(root / "docs/GRPC.md").write_text("\n".join(out))
print("ok")
