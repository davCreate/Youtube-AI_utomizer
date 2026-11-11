from datetime import datetime, timezone

import pytest

from yt_automizer import ledger
from yt_automizer.compliance import UploadPlan
from yt_automizer.config import Settings
from yt_automizer.niche import score_videos
from yt_automizer.service import PolicyBlocked, YouTubeService

NOW = datetime(2026, 11, 11, tzinfo=timezone.utc)


def vid(views, subs, ch, published="2026-11-01T00:00:00Z"):
    return {"views": views, "channel_subs": subs, "channel_id": ch, "published_at": published}


def test_small_channels_winning_scores_higher():
    open_niche = [vid(200_000, 3_000, f"c{i}") for i in range(10)]
    saturated = [vid(200_000, 5_000_000, "big") for _ in range(10)]
    assert score_videos(open_niche, NOW)["score"] > score_videos(saturated, NOW)["score"]


def test_empty():
    assert score_videos([], NOW)["score"] == 0.0


# ----------------------------------------------------------- fake API client
class Call:
    def __init__(self, result):
        self.result = result

    def execute(self):
        return self.result


class Resource:
    def __init__(self, log, name, results):
        self.log, self.name, self.results = log, name, results

    def __getattr__(self, method):
        def call(**kw):
            self.log.append((self.name, method, kw))
            return Call(self.results.get((self.name, method), {}))
        return call


class FakeYT:
    def __init__(self, results):
        self.log, self.results = [], results

    def __getattr__(self, name):
        return lambda: Resource(self.log, name, self.results)


CHANNEL = {"items": [{"id": "UC1", "snippet": {"title": "Aero Lab"},
                      "statistics": {"subscriberCount": "1200", "viewCount": "50000", "videoCount": "12"},
                      "contentDetails": {"relatedPlaylists": {"uploads": "UU1"}}, "status": {}}]}


@pytest.fixture(autouse=True)
def tmp_home(tmp_path, monkeypatch):
    monkeypatch.setenv("YT_AUTOMIZER_HOME", str(tmp_path))


def test_overview_and_quota():
    svc = YouTubeService(FakeYT({("channels", "list"): CHANNEL}), None, Settings())
    assert svc.channel_overview()["subscribers"] == 1200
    assert ledger.quota_used() == 1


def test_upload_blocked_before_any_api_write(tmp_path):
    f = tmp_path / "v.mp4"
    f.write_bytes(b"0")
    yt = FakeYT({("channels", "list"): CHANNEL, ("playlistItems", "list"): {"items": []}})
    svc = YouTubeService(yt, None, Settings())
    with pytest.raises(PolicyBlocked):
        svc.upload(str(f), UploadPlan(title="t"))
    assert not any(m == "insert" for _, m, _ in yt.log)


def test_publish_keeps_disclosure_flag():
    video = {"items": [{"snippet": {}, "status": {"privacyStatus": "private", "containsSyntheticMedia": True,
                                                  "selfDeclaredMadeForKids": False}}]}
    yt = FakeYT({("videos", "list"): video, ("videos", "update"): {}})
    YouTubeService(yt, None, Settings()).publish("abc")
    body = [kw for n, m, kw in yt.log if m == "update"][0]["body"]
    assert body["status"] == {"privacyStatus": "public", "containsSyntheticMedia": True, "selfDeclaredMadeForKids": False}
    assert ledger.read_audit()[-1]["action"] == "publish"


def test_server_imports_and_registers_tools():
    from yt_automizer import server
    assert server.mcp is not None
