"""Smoke test das rotas usadas pelo frontend AviaWatch."""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"


def req(method: str, path: str, body: dict | None = None) -> tuple[int, object]:
    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(
        BASE + path, data=data, headers=headers, method=method
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            raw = response.read().decode("utf-8")
            payload: object
            try:
                payload = json.loads(raw) if raw else None
            except json.JSONDecodeError:
                payload = raw
            return response.status, payload
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = raw
        return exc.code, payload


def main() -> int:
    print(f"Base: {BASE}")
    failed = 0

    paths = [
        "/api/health",
        "/api/cameras",
        "/api/visits",
        "/api/stats",
        "/api/settings",
    ]
    # /health (sem /api) só existe no backend direto — o Vite faz proxy de /api e /captures
    if ":5173" not in BASE:
        paths.append("/health")

    for path in paths:
        status, _ = req("GET", path)
        ok = status == 200
        print(("OK" if ok else "FAIL"), status, "GET", path)
        failed += 0 if ok else 1

    status, cam = req(
        "POST",
        "/api/cameras",
        {
            "name": "Teste Etapa4",
            "source_type": "usb",
            "stream_url": "1",
            "enabled": False,
        },
    )
    ok = status == 201 and isinstance(cam, dict) and "id" in cam
    print(("OK" if ok else "FAIL"), status, "POST /api/cameras", cam if not ok else "")
    failed += 0 if ok else 1

    cam_id = cam.get("id") if isinstance(cam, dict) else None
    if cam_id:
        status, _ = req("PUT", f"/api/cameras/{cam_id}", {"enabled": False})
        ok = status == 200
        print(("OK" if ok else "FAIL"), status, "PUT /api/cameras/{id}")
        failed += 0 if ok else 1

        status, _ = req("DELETE", f"/api/cameras/{cam_id}")
        ok = status == 204
        print(("OK" if ok else "FAIL"), status, "DELETE /api/cameras/{id}")
        failed += 0 if ok else 1

    status, _ = req("PUT", "/api/settings", {"notifications_enabled": True})
    ok = status == 200
    print(("OK" if ok else "FAIL"), status, "PUT /api/settings")
    failed += 0 if ok else 1

    status, payload = req("POST", "/api/settings/test-notification", {"channel": "telegram"})
    # 400 esperado quando .env não tem Telegram
    ok = status in {200, 400}
    print(("OK" if ok else "FAIL"), status, "POST /api/settings/test-notification", payload)
    failed += 0 if ok else 1

    print("RESULT:", "PASS" if failed == 0 else f"FAIL ({failed})")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
