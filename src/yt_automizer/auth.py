"""OAuth 2.0 for the YouTube Data API and YouTube Analytics API.

The first login runs from `yt-automizer setup`. Afterwards the saved token is refreshed
silently; if it ever stops working, the browser opens again on this PC to log back in.
"""

from __future__ import annotations

import contextlib
import sys

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

from . import config

SCOPES = [
    # Manage videos, playlists, comments (needed for metadata edits and replies).
    "https://www.googleapis.com/auth/youtube.force-ssl",
    # Upload videos.
    "https://www.googleapis.com/auth/youtube.upload",
    # Views, watch time, retention, traffic sources...
    "https://www.googleapis.com/auth/yt-analytics.readonly",
    # Estimated revenue, RPM, CPM (only returns data once the channel is in YPP).
    "https://www.googleapis.com/auth/yt-analytics-monetary.readonly",
]


class NotAuthenticated(RuntimeError):
    pass


def run_login_flow(open_browser: bool = True, timeout_seconds: int | None = None) -> Credentials:
    from google_auth_oauthlib.flow import InstalledAppFlow

    secret = config.client_secret_path()
    if not secret.exists():
        raise FileNotFoundError(
            f"OAuth client file not found at {secret}. Create a 'Desktop app' OAuth client in "
            "Google Cloud Console (APIs: YouTube Data API v3 + YouTube Analytics API), download "
            "the JSON and save it there, or set YT_AUTOMIZER_CLIENT_SECRET."
        )
    flow = InstalledAppFlow.from_client_secrets_file(str(secret), SCOPES)
    # stdout is the MCP channel when running as a server, so every message goes to stderr.
    with contextlib.redirect_stdout(sys.stderr):
        creds = flow.run_local_server(
            port=0, open_browser=open_browser, prompt="consent", timeout_seconds=timeout_seconds,
            authorization_prompt_message="Si el navegador no se abre, visita: {url}",
            success_message="Conectado. Ya puedes cerrar esta pestaña y volver a Claude Code.",
        )
    config.token_path().write_text(creds.to_json())
    config.token_path().chmod(0o600)
    return creds


def load_credentials(allow_browser_login: bool = True) -> Credentials:
    path = config.token_path()
    creds = None
    if path.exists():
        creds = Credentials.from_authorized_user_file(str(path), SCOPES)
        if not creds.valid and creds.refresh_token:
            try:
                creds.refresh(Request())
                path.write_text(creds.to_json())
            except Exception:  # revoked, or 7-day expiry of an app left in "Testing"
                creds = None
    if creds is not None and creds.valid:
        return creds
    if allow_browser_login and config.client_secret_path().exists():
        return run_login_flow(timeout_seconds=300)
    raise NotAuthenticated("YouTube no está conectado. Ejecuta `yt-automizer setup` (o haz doble clic en instalar).")


def build_clients():
    """Return (youtube_data_v3, youtube_analytics_v2) API resources."""
    from googleapiclient.discovery import build

    creds = load_credentials()
    youtube = build("youtube", "v3", credentials=creds, cache_discovery=False)
    analytics = build("youtubeAnalytics", "v2", credentials=creds, cache_discovery=False)
    return youtube, analytics
