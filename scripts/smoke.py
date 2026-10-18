"""Сквозная проверка поднятого стенда через Gateway.

make smoke                         # http://localhost:8000
make smoke URL=http://1.2.3.4      # сервер после деплоя (через nginx фронта)
"""

import sys
import uuid

import httpx

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000").rstrip("/")


def check(cond: bool, what: str) -> None:
    print(("  ok   " if cond else "  FAIL ") + what)
    if not cond:
        raise SystemExit(1)


def main() -> None:
    print(f"Smoke test against {BASE}")
    with httpx.Client(base_url=BASE, timeout=10) as c:
        ready = c.get("/health/ready").json()
        print(f"  ready: {ready}")

        email = f"smoke-{uuid.uuid4().hex[:8]}@example.com"
        r = c.post(
            "/api/v1/auth/register",
            json={"email": email, "name": "Smoke", "password": "password123"},
        )
        check(r.status_code == 201, f"register {r.status_code}")
        check("refresh_token" in c.cookies, "refresh cookie set")

        r = c.post(
            "/api/v1/auth/register",
            json={"email": email, "name": "Smoke", "password": "password123"},
        )
        check(r.json()["error"]["code"] == "EMAIL_TAKEN", "duplicate email -> EMAIL_TAKEN")

        r = c.post("/api/v1/auth/login", json={"email": email, "password": "password123"})
        check(r.status_code == 200, "login")
        auth = {"Authorization": f"Bearer {r.json()['access_token']}"}

        r = c.get("/api/v1/users/me", headers=auth)
        check(r.status_code == 200 and r.json()["email"] == email, "users/me")

        r = c.post("/api/v1/items", json={"title": "Smoke item"}, headers=auth)
        check(r.status_code == 201, "create item")
        item_id = r.json()["id"]

        r = c.get(f"/api/v1/items/{item_id}", headers=auth)
        check(r.json().get("owner_name") == "Smoke", "get item (+owner_name from auth via gRPC)")

        r = c.get("/api/v1/items?limit=1", headers=auth)
        check(r.status_code == 200 and len(r.json()["items"]) == 1, "list items")

        r = c.patch(f"/api/v1/items/{item_id}", json={"status": "done"}, headers=auth)
        check(r.json().get("status") == "done", "mark done")
        r = c.patch(f"/api/v1/items/{item_id}", json={"title": "x"}, headers=auth)
        check(
            r.status_code == 409 and r.json()["error"]["code"] == "ITEM_IS_DONE", "409 ITEM_IS_DONE"
        )

        r = c.get(f"/api/v1/items/{uuid.uuid4()}", headers=auth)
        check(
            r.status_code == 404 and r.json()["error"]["code"] == "ITEM_NOT_FOUND",
            "404 ITEM_NOT_FOUND",
        )

        r = c.post("/api/v1/auth/refresh")
        check(r.status_code == 200 and r.json()["access_token"], "refresh by cookie")

        r = c.post("/api/v1/auth/logout")
        check(r.status_code == 204, "logout")
        r = c.post("/api/v1/auth/refresh")
        check(r.status_code == 401, "refresh after logout -> 401")

        r = c.delete(f"/api/v1/items/{item_id}", headers=auth)
        check(r.status_code == 204, "delete item")
    print("All good")


if __name__ == "__main__":
    main()
