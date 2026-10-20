"""Токен пользователя VK через приложение VK ID (OAuth 2.1 + PKCE) — без сервисного ключа.

Сервисный ключ VK выдаёт только подтверждённому бизнес-аккаунту. Токен пользователя выдаёт любое
приложение VK ID после входа обычным аккаунтом — им сборщик ходит в VK API так же.

    python3 scripts/vk_token.py               # ссылка для входа → адрес после входа → токен
    python3 scripts/vk_token.py --refresh     # новый токен по refresh_token (без входа)
    python3 scripts/vk_token.py --check       # проверить сохранённый токен, ничего не меняя

Токен сохраняется в .vk/token.json (в .gitignore). Сборщик (compose: том ./.vk:/vk) читает его
и сам обновляет каждый час — входить заново нужно, только если VK отзовёт вход.
--write-env дополнительно пишет токен в .env (VK_SERVICE_TOKEN) — для запуска без файла, на час.

Только стандартная библиотека Python.
Настройки: VK_CLIENT_ID (по умолчанию 54832790, MediaPulse), VK_REDIRECT_URI (https://localhost) —
адрес должен совпадать с «Доверенным Redirect URL» в настройках приложения VK ID.
"""

import argparse
import base64
import hashlib
import json
import os
import secrets
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATE_FILE = ROOT / ".vk" / "token.json"
LEGACY_FILE = (
    ROOT / ".vk_token.json"
)  # первая версия скрипта хранила только refresh_token
ENV_FILE = ROOT / ".env"
CLIENT_ID = os.environ.get("VK_CLIENT_ID", "54832790")
REDIRECT_URI = os.environ.get("VK_REDIRECT_URI", "https://localhost")
SCOPES = "wall groups"
AUTH_URL = "https://id.vk.com/authorize"
TOKEN_URL = "https://id.vk.com/oauth2/auth"
API = "https://api.vk.com/method/"


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def post_form(url: str, form: dict[str, str]) -> dict[str, object]:
    body = urllib.parse.urlencode(form).encode()
    request = urllib.request.Request(url, data=body, method="POST")
    request.add_header("Content-Type", "application/x-www-form-urlencoded")
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode())
    except urllib.error.HTTPError as e:
        return json.loads(e.read().decode() or "{}")


def api(method: str, token: str, **params: str) -> dict[str, object]:
    query = urllib.parse.urlencode({**params, "v": "5.199", "access_token": token})
    with urllib.request.urlopen(f"{API}{method}?{query}", timeout=20) as response:
        return json.loads(response.read().decode())


def login() -> dict[str, object]:
    verifier = b64url(secrets.token_bytes(48))
    challenge = b64url(hashlib.sha256(verifier.encode()).digest())
    state = b64url(secrets.token_bytes(16))
    url = (
        AUTH_URL
        + "?"
        + urllib.parse.urlencode(
            {
                "response_type": "code",
                "client_id": CLIENT_ID,
                "scope": SCOPES,
                "redirect_uri": REDIRECT_URI,
                "state": state,
                "code_challenge": challenge,
                "code_challenge_method": "S256",
            }
        )
    )
    print("1) Откройте ссылку в браузере, где вы вошли в VK, и разрешите доступ:\n")
    print(url)
    print(
        f"\n2) Браузер перейдёт на {REDIRECT_URI}/?code=… — страница не откроется, это нормально.\n"
        "   Скопируйте адрес целиком из строки браузера и вставьте сюда."
    )
    returned = input("\nАдрес: ").strip()
    params = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(returned).query))
    if "payload" in params:  # некоторые версии VK ID отдают всё одним JSON в payload
        params.update({k: str(v) for k, v in json.loads(params["payload"]).items()})
    if params.get("state") != state:
        sys.exit(
            "state не совпал — вставлен адрес не от этой ссылки. Запустите скрипт заново."
        )
    if "code" not in params or "device_id" not in params:
        sys.exit(f"В адресе нет code / device_id: {sorted(params)}")
    tokens = post_form(
        TOKEN_URL,
        {
            "grant_type": "authorization_code",
            "code_verifier": verifier,
            "redirect_uri": REDIRECT_URI,
            "code": params["code"],
            "client_id": CLIENT_ID,
            "device_id": params["device_id"],
            "state": state,
        },
    )
    tokens["device_id"] = params["device_id"]
    return tokens


def load_state() -> dict[str, object]:
    for path in (STATE_FILE, LEGACY_FILE):
        if path.exists():
            return dict(json.loads(path.read_text()))
    sys.exit("Нет сохранённого токена — сначала войдите: python3 scripts/vk_token.py")


def save_state(tokens: dict[str, object]) -> None:
    expires_in = tokens.get("expires_in")
    state = {
        "access_token": tokens["access_token"],
        "expires_at": int(time.time())
        + (expires_in if isinstance(expires_in, int) else 3600),
        "refresh_token": tokens.get("refresh_token", ""),
        "device_id": tokens.get("device_id", ""),
    }
    STATE_FILE.parent.mkdir(exist_ok=True)
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state))
    tmp.chmod(0o600)
    os.replace(tmp, STATE_FILE)
    print(f"Сохранено в {STATE_FILE.relative_to(ROOT)} — сборщик подхватит сам")


def refresh() -> dict[str, object]:
    saved = load_state()
    tokens = post_form(
        TOKEN_URL,
        {
            "grant_type": "refresh_token",
            "refresh_token": str(saved["refresh_token"]),
            "client_id": CLIENT_ID,
            "device_id": str(saved["device_id"]),
            "state": b64url(secrets.token_bytes(16)),
        },
    )
    tokens["device_id"] = saved["device_id"]
    return tokens


def write_env(token: str) -> None:
    lines = ENV_FILE.read_text().splitlines() if ENV_FILE.exists() else []
    lines = [line for line in lines if not line.startswith("VK_SERVICE_TOKEN=")]
    lines.append(f"VK_SERVICE_TOKEN={token}")
    ENV_FILE.write_text("\n".join(lines) + "\n")
    print(f"Токен записан в {ENV_FILE} → docker compose up -d collector_service")


def check(token: str) -> None:
    print("\nПроверка токена в VK API:")
    for method, params in (
        ("groups.getById", {"group_id": "vk"}),
        ("wall.get", {"domain": "vk", "count": "1"}),
        ("newsfeed.search", {"q": "Красноярск", "count": "1"}),
    ):
        answer = api(method, token, **params)
        if "response" in answer:
            print(f"  ok    {method}")
        else:
            error = answer.get("error", {})
            code = error.get("error_code") if isinstance(error, dict) else "?"
            msg = error.get("error_msg") if isinstance(error, dict) else answer
            print(f"  FAIL  {method}: ошибка {code} — {msg}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--refresh", action="store_true", help="обновить токен без входа"
    )
    parser.add_argument(
        "--write-env", action="store_true", help="записать токен в .env"
    )
    parser.add_argument(
        "--check", action="store_true", help="проверить сохранённый токен"
    )
    args = parser.parse_args()

    if args.check:
        saved = load_state()
        left = int(saved.get("expires_at", 0)) - int(time.time())  # type: ignore[call-overload]
        print(
            f"Токен {'действует ещё ' + str(left // 60) + ' мин' if left > 0 else 'истёк'}"
        )
        if left > 0:
            check(str(saved["access_token"]))
        return

    tokens = refresh() if args.refresh else login()
    if "access_token" not in tokens:
        sys.exit(
            f"VK ID не выдал токен: {json.dumps(tokens, ensure_ascii=False)[:500]}"
        )
    token = str(tokens["access_token"])
    save_state(tokens)
    print(
        f"\nТокен получен: {token[:8]}… (живёт {tokens.get('expires_in', '?')} с, "
        f"права: {tokens.get('scope', '?')})"
    )
    check(token)
    if args.write_env:
        write_env(token)
    else:
        print("\nДальше: docker compose up -d --build collector_service")


if __name__ == "__main__":
    main()
