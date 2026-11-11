"""Paths and tunable settings. Everything lives in one local folder, outside the repo."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path


def home_dir() -> Path:
    path = Path(os.environ.get("YT_AUTOMIZER_HOME", Path.home() / ".yt-automizer")).expanduser()
    path.mkdir(parents=True, exist_ok=True)
    return path


def client_secret_path() -> Path:
    return Path(os.environ.get("YT_AUTOMIZER_CLIENT_SECRET", home_dir() / "client_secret.json")).expanduser()


def token_path() -> Path:
    return home_dir() / "token.json"


def audit_log_path() -> Path:
    return home_dir() / "audit.jsonl"


def quota_path() -> Path:
    return home_dir() / "quota.json"


@dataclass
class Settings:
    # Uploads per rolling 24h. Low on purpose: volume without originality is what
    # YouTube's "inauthentic content" rule demonetizes.
    max_uploads_per_day: int = 3
    # Text similarity (0-1) against recent uploads above which an upload is blocked / warned.
    similarity_block: float = 0.80
    similarity_warn: float = 0.60
    # Minimum length of the written description of the human's creative contribution.
    min_human_contribution_chars: int = 40
    # Daily YouTube Data API quota (default project quota is 10,000 units).
    daily_quota: int = 10_000
    # Topics where YouTube asks for extra care with AI narration / personas.
    sensitive_topics: list[str] = field(
        default_factory=lambda: [
            "health", "medical", "medicine", "doctor", "diet", "cure",
            "finance", "investing", "stock", "crypto", "loan", "tax",
            "election", "vote", "politics", "news", "war", "breaking",
            "salud", "medicina", "finanzas", "inversión", "elecciones", "noticias",
        ]
    )


def load_settings() -> Settings:
    path = home_dir() / "settings.json"
    if not path.exists():
        return Settings()
    data = json.loads(path.read_text())
    known = {k: v for k, v in data.items() if k in Settings.__dataclass_fields__}
    return Settings(**known)


def save_default_settings() -> Path:
    path = home_dir() / "settings.json"
    if not path.exists():
        path.write_text(json.dumps(asdict(Settings()), indent=2, ensure_ascii=False))
    return path
