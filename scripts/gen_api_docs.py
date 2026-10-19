"""openapi.yaml -> docs/API.md + docs/api-types.ts"""

import json
import pathlib
import sys

import yaml

root = (
    pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else pathlib.Path(__file__).resolve().parents[1]
)
spec = yaml.safe_load((root / "contracts/http/openapi.yaml").read_text())
S = spec["components"]["schemas"]
P = spec["components"]["parameters"]


def deref(o):
    if isinstance(o, dict) and "$ref" in o:
        node = spec
        for part in o["$ref"][2:].split("/"):
            node = node[part]
        return node
    return o


def refname(o):
    return o["$ref"].split("/")[-1]


def t_md(s):
    """schema -> readable type"""
    if "$ref" in s:
        return f"[`{refname(s)}`](#{refname(s).lower()})"
    if "oneOf" in s:
        parts = [t_md(x) for x in s["oneOf"]]
        return " \\| ".join(parts)
    typ = s.get("type")
    if isinstance(typ, list):
        base = [x for x in typ if x != "null"]
        sub = dict(s)
        sub["type"] = base[0] if base else "null"
        if "enum" in sub:
            sub["enum"] = [e for e in sub["enum"] if e is not None]
        return t_md(sub) + (" \\| null" if "null" in typ else "")
    if typ == "null":
        return "null"
    if "enum" in s:
        return " \\| ".join(f"`{e}`" for e in s["enum"])
    if typ == "array":
        return t_md(s["items"]) + "[]"
    if typ == "object" and "properties" in s:
        return "object (см. ниже)"
    fmt = s.get("format")
    return f"{typ}" + (f" ({fmt})" if fmt else "")


def t_ts(s):
    if "$ref" in s:
        return refname(s)
    if "oneOf" in s:
        return " | ".join(t_ts(x) for x in s["oneOf"])
    typ = s.get("type")
    if isinstance(typ, list):
        base = [x for x in typ if x != "null"]
        sub = dict(s)
        sub["type"] = base[0]
        if "enum" in sub:
            sub["enum"] = [e for e in sub["enum"] if e is not None]
        return t_ts(sub) + (" | null" if "null" in typ else "")
    if typ == "null":
        return "null"
    if "enum" in s:
        return " | ".join(f'"{e}"' for e in s["enum"])
    if typ == "array":
        inner = t_ts(s["items"])
        return f"({inner})[]" if "|" in inner else f"{inner}[]"
    if typ in ("integer", "number"):
        return "number"
    if typ == "boolean":
        return "boolean"
    if typ == "string":
        return "string"
    if typ == "object":
        if "properties" in s:
            req = set(s.get("required", []))
            inner = "; ".join(
                f"{k}{'' if k in req else '?'}: {t_ts(v)}" for k, v in s["properties"].items()
            )
            return "{ " + inner + " }"
        return "Record<string, unknown>"
    return "unknown"


def desc(s):
    d = s.get("description", "")
    extra = []
    if "default" in s:
        extra.append("по умолчанию `" + json.dumps(s["default"], ensure_ascii=False) + "`")
    for k, w in (
        ("minLength", "мин. длина"),
        ("maxLength", "макс. длина"),
        ("minimum", "мин."),
        ("maximum", "макс."),
        ("minItems", "мин. элементов"),
    ):
        if k in s:
            extra.append(f"{w} {s[k]}")
    d = d.replace("\n", " ").strip()
    return "; ".join(x for x in [d] + extra if x).replace("|", "\\|")


def obj_table(s, indent=""):
    s = deref(s)
    req = set(s.get("required", []))
    rows = ["| Поле | Тип | Обяз. | Описание |", "|---|---|---|---|"]
    nested = []
    for k, v in s.get("properties", {}).items():
        rows.append(f"| `{k}` | {t_md(v)} | {'да' if k in req else 'нет'} | {desc(v)} |")
        if v.get("type") == "object" and "properties" in v:
            nested.append((k, v))
    out = "\n".join(rows)
    for k, v in nested:
        out += f"\n\n`{k}`:\n\n" + obj_table(v)
    return out


md = []
md.append("# HTTP API — справочник (сгенерирован из `contracts/http/openapi.yaml`)\n")
md.append(
    "> Не править руками. Источник правды — `openapi.yaml`; после его изменения: "
    "`make docs` (или `make proto`).\n"
)
md.append(
    f"Версия контракта: **{spec['info']['version']}**. Базовый URL: gateway `http://localhost:8000`, мок Prism `http://localhost:4010`.\n"
)
md.append(
    "Общие правила:\n\n"
    + spec["info"]["description"].split("Общие правила:")[1].split("Изменения контракта")[0].strip()
    + "\n"
)
md.append(
    "TypeScript-типы всех схем — [`api-types.ts`](api-types.ts) (для фронта предпочтительно генерировать `openapi-typescript`, этот файл — для чтения).\n"
)
md.append("## Содержание\n")
md.append("| Метод | Путь | operationId | Что делает |\n|---|---|---|---|")
eps = []
for path, item in spec["paths"].items():
    common = item.get("parameters", [])
    for m in ("get", "post", "patch", "delete", "put"):
        if m not in item:
            continue
        op = item[m]
        anchor = op["operationId"].lower()
        md.append(
            f"| {m.upper()} | `{path}` | [{op['operationId']}](#{anchor}) | {op.get('summary', '').replace('|', '/')} |"
        )
        eps.append((path, m, op, common))
md.append("")
for path, m, op, common in eps:
    md.append(f"## {op['operationId']}\n")
    md.append(f"**`{m.upper()} {path}`** — {op.get('summary', '')}\n")
    if op.get("description"):
        md.append(op["description"].strip() + "\n")
    params = [deref(p) for p in common + op.get("parameters", [])]
    if params:
        md.append("Параметры:\n\n| Имя | Где | Тип | Обяз. | Описание |\n|---|---|---|---|---|")
        for p in params:
            sch = p["schema"]
            ty = t_md(sch)
            note = desc(sch) or ""
            if p.get("description"):
                note = p["description"].replace("|", "\\|") + ("; " + note if note else "")
            if sch.get("type") == "array" and p.get("explode"):
                note += ("; " if note else "") + f"повторять: `?{p['name']}=a&{p['name']}=b`"
            md.append(
                f"| `{p['name']}` | {p['in']} | {ty} | {'да' if p.get('required') else 'нет'} | {note} |"
            )
        md.append("")
    rb = op.get("requestBody")
    if rb:
        for ct, c in rb["content"].items():
            sch = c["schema"]
            name = refname(sch) if "$ref" in sch else None
            md.append(f"Тело (`{ct}`): " + (f"[`{name}`](#{name.lower()})" if name else "") + "\n")
            if not name:
                md.append(obj_table(sch) + "\n")
            ex = c.get("example") or (
                next(iter(c.get("examples", {}).values()))["value"] if c.get("examples") else None
            )
            if ex is not None:
                import json

                md.append("```json\n" + json.dumps(ex, ensure_ascii=False, indent=2) + "\n```\n")
    md.append("Ответы:\n\n| Код | Тело |\n|---|---|")
    for code, r in op["responses"].items():
        rr = deref(r)
        body = "—"
        if "content" in rr:
            ct, c = next(iter(rr["content"].items()))
            sch = c["schema"]
            if "$ref" in sch:
                body = f"[`{refname(sch)}`](#{refname(sch).lower()})"
            elif sch.get("type") == "array":
                body = t_md(sch)
            elif sch.get("format") == "binary":
                body = "файл: " + ", ".join(f"`{k}`" for k in rr["content"])
            else:
                body = "`" + t_ts(sch) + "`"
            if "$ref" in r:
                body += f" ({rr.get('description', '')})"
        else:
            body = rr.get("description", "—")
        md.append(f"| {code} | {body} |")
    md.append("")
md.append("# Схемы\n")
for name, s in S.items():
    md.append(f"## {name}\n")
    if s.get("description"):
        md.append(s["description"].strip() + "\n")
    if "enum" in s:
        md.append("Значения: " + ", ".join(f"`{e}`" for e in s["enum"]) + "\n")
    elif s.get("type") == "object":
        md.append(obj_table(s) + "\n")
    if "example" in s:
        import json

        md.append(
            "<details><summary>Пример</summary>\n\n```json\n"
            + json.dumps(s["example"], ensure_ascii=False, indent=2)
            + "\n```\n</details>\n"
        )
(root / "docs/API.md").write_text("\n".join(md))

ts = [
    "// Сгенерировано из contracts/http/openapi.yaml — не править руками.",
    f"// Версия контракта {spec['info']['version']}. Для кода фронта используйте openapi-typescript (FE-01).",
    "",
]
for name, s in S.items():
    d = s.get("description")
    if d:
        ts.append("/** " + d.strip().replace("\n", " ") + " */")
    if "enum" in s or s.get("type") != "object":
        ts.append(f"export type {name} = {t_ts(s)};\n")
        continue
    ts.append(f"export interface {name} {{")
    req = set(s.get("required", []))
    for k, v in s.get("properties", {}).items():
        dd = v.get("description")
        if dd:
            ts.append("  /** " + dd.strip().replace("\n", " ") + " */")
        ts.append(f"  {k}{'' if k in req else '?'}: {t_ts(v)};")
    ts.append("}\n")
(root / "docs/api-types.ts").write_text("\n".join(ts))
print("ok", len(eps), "endpoints", len(S), "schemas")
