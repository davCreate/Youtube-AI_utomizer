"""OAuth 2.0 for the YouTube Data API and YouTube Analytics API.

The interactive login runs once from the CLI (`yt-automizer auth`). The MCP server
only reuses and refreshes the saved token; it never opens a browser itself.
"""

from __future__ import annotations

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


def run_login_flow(open_browser: bool = True) -> Credentials:
    from google_auth_oauthlib.flow import InstalledAppFlow

    secret = config.client_secret_path()
    if not secret.exists():
        raise FileNotFoundError(
            f"OAuth client file not found at {secret}. Create a 'Desktop app' OAuth client in "
            "Google Cloud Console (APIs: YouTube Data API v3 + YouTube Analytics API), download "
            "the JSON and save it there, or set YT_AUTOMIZER_CLIENT_SECRET."
        )
    flow = InstalledAppFlow.from_client_secrets_file(str(secret), SCOPES)
    creds = flow.run_local_server(port=0, open_browser=open_browser, prompt="consent")
    config.token_path().write_text(creds.to_json())
    config.token_path().chmod(0o600)
    return creds


def load_credentials() -> Credentials:
    path = config.token_path()
    if not path.exists():
        raise NotAuthenticated("No saved login. Run `yt-automizer auth` in a terminal first.")
    creds = Credentials.from_authorized_user_file(str(path), SCOPES)
    if not creds.valid:
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            path.write_text(creds.to_json())
        else:
            raise NotAuthenticated("Saved login is invalid. Run `yt-automizer auth` again.")
    return creds


def build_clients():
    """Return (youtube_data_v3, youtube_analytics_v2) API resources."""
    from googleapiclient.discovery import build

    creds = load_credentials()
    youtube = build("youtube", "v3", credentials=creds, cache_discovery=False)
    analytics = build("youtubeAnalytics", "v2", credentials=creds, cache_discovery=False)
    return youtube, analytics
