"""WASH module: post occupancy monitor."""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

API_BASE = os.environ.get("API_BASE_URL", "http://dynamic-api:3001").rstrip("/")
DATA_DIR = os.environ.get("MODULE_DATA_DIR", "/data")
POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL", "60"))


def fetch_post_states() -> list[dict]:
    url = f"{API_BASE}/api/crm/post-states?limit=500"
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    if isinstance(payload, dict) and "data" in payload:
        return payload["data"] if isinstance(payload["data"], list) else []
    if isinstance(payload, list):
        return payload
    return []


def post_busy(state: dict | None) -> bool:
    if not state:
        return False
    connected = state.get("connected")
    if connected is False:
        return False
    mode = str(state.get("mode") or state.get("modeName") or "").lower()
    mode_num = state.get("modeNumber")
    if mode_num == 9 or "program_9" in mode or mode == "9":
        return False
    return True


def build_snapshot(states: list[dict]) -> dict:
    total = len(states)
    busy = sum(1 for s in states if post_busy(s))
    free = sum(1 for s in states if s and not post_busy(s) and s.get("connected") is not False)
    offline = total - busy - free
    return {
        "recordedAt": datetime.now(timezone.utc).isoformat(),
        "total": total,
        "busy": busy,
        "free": free,
        "offline": max(0, offline),
        "posts": [
            {
                "postId": s.get("postId"),
                "washId": s.get("washId"),
                "busy": post_busy(s),
                "mode": s.get("mode") or s.get("modeName"),
            }
            for s in states[:50]
        ],
    }


def save_snapshot(snapshot: dict) -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    path = os.path.join(DATA_DIR, "last_snapshot.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=2)


def main() -> None:
    while True:
        try:
            states = fetch_post_states()
            snapshot = build_snapshot(states)
            save_snapshot(snapshot)
            print(f"[post-occupancy] total={snapshot['total']} busy={snapshot['busy']} free={snapshot['free']}")
        except urllib.error.URLError as err:
            print(f"[post-occupancy] API error: {err}")
        except Exception as err:  # noqa: BLE001
            print(f"[post-occupancy] error: {err}")
        time.sleep(max(15, POLL_INTERVAL))


if __name__ == "__main__":
    main()
