import json
import os
import sys

from yt_automizer.setup_wizard import find_downloaded_secret, is_client_secret, mcp_command

DESKTOP = {"installed": {"client_id": "x.apps.googleusercontent.com", "client_secret": "s"}}
WEB = {"web": {"client_id": "x"}}


def test_finds_newest_desktop_client(tmp_path):
    old = tmp_path / "client_secret_old.json"
    old.write_text(json.dumps(DESKTOP))
    os.utime(old, (1000, 1000))
    web = tmp_path / "client_secret_web.json"
    web.write_text(json.dumps(WEB))
    new = tmp_path / "client_secret_123.apps.googleusercontent.com.json"
    new.write_text(json.dumps(DESKTOP))
    assert find_downloaded_secret([tmp_path, tmp_path / "missing"], since=2000) == new
    assert not is_client_secret(web)


def test_nothing_found(tmp_path):
    assert find_downloaded_secret([tmp_path], since=0) is None


def test_mcp_command_uses_this_python():
    assert mcp_command() == [sys.executable, "-m", "yt_automizer", "serve"]


def test_mcp_command_when_packaged(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "YouTube-AI-utomizer.exe"))
    (cmd,) = mcp_command()
    assert cmd.startswith(str(tmp_path)) and "yt-automizer-server" in cmd
