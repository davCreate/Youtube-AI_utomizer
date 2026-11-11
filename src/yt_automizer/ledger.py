"""Local audit log of every write action, and a YouTube API quota estimate."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import config

# Unit costs from the YouTube Data API quota calculator. videos.insert has been
# 1600 units for years; adjust here if Google changes it.
QUOTA_COST = {
    "search.list": 100,
    "videos.list": 1,
    "channels.list": 1,
    "playlistItems.list": 1,
    "commentThreads.list": 1,
    "comments.insert": 50,
    "videos.update": 50,
    "videos.insert": 1600,
    "thumbnails.set": 50,
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def audit(action: str, details: dict, path: Path | None = None) -> None:
    path = path or config.audit_log_path()
    entry = {"ts": _now().isoformat(), "action": action, **details}
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def read_audit(limit: int = 50, path: Path | None = None) -> list[dict]:
    path = path or config.audit_log_path()
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()[-limit:]
    return [json.loads(line) for line in lines if line.strip()]


def uploads_in_last_24h(path: Path | None = None) -> int:
    cutoff = _now() - timedelta(hours=24)
    return sum(
        1
        for e in read_audit(limit=1000, path=path)
        if e["action"] == "upload" and datetime.fromisoformat(e["ts"]) >= cutoff
    )


def _quota_day() -> str:
    # The quota resets at midnight Pacific time; UTC-8 is close enough for an estimate.
    return (_now() - timedelta(hours=8)).date().isoformat()


def spend_quota(method: str, times: int = 1, path: Path | None = None) -> int:
    path = path or config.quota_path()
    data = json.loads(path.read_text()) if path.exists() else {}
    day = _quota_day()
    if data.get("day") != day:
        data = {"day": day, "used": 0}
    data["used"] += QUOTA_COST.get(method, 1) * times
    path.write_text(json.dumps(data))
    return data["used"]


def quota_used(path: Path | None = None) -> int:
    path = path or config.quota_path()
    if not path.exists():
        return 0
    data = json.loads(path.read_text())
    return data["used"] if data.get("day") == _quota_day() else 0
