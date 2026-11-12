import io
import json
import urllib.error
import zipfile
from pathlib import Path

import pytest

from yt_automizer import updater


def release(tag, assets=()):
    return json.dumps({"tag_name": tag, "body": "Novedades", "html_url": "https://x/rel",
                       "zipball_url": "https://x/src.zip",
                       "assets": [{"name": n, "browser_download_url": f"https://x/{n}"} for n in assets]}).encode()


def test_versions():
    assert updater.parse_version("v0.10.0") > updater.parse_version("0.9.9")
    assert updater.parse_version("v1.2.3-beta") == (1, 2, 3)


def test_newer_release_found():
    info = updater.check("0.2.0", fetch=lambda url, **k: release("v0.3.0", [updater.WINDOWS_ASSET, "other.zip"]))
    assert info.available and info.latest == "0.3.0"
    assert info.asset_url.endswith(updater.WINDOWS_ASSET)


def test_same_version_no_update():
    assert not updater.check("0.3.0", fetch=lambda url, **k: release("v0.3.0")).available


def test_no_releases_yet():
    def fetch(url, **k):
        raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)
    info = updater.check("0.2.0", fetch=fetch)
    assert not info.available and "Todavía" in info.notes


def zip_bytes(files):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, data in files.items():
            z.writestr(name, data)
    return buf.getvalue()


def test_source_zip_unwraps_top_folder():
    data = zip_bytes({"repo-abc/pyproject.toml": "x", "repo-abc/src/yt_automizer/__init__.py": ""})
    out = updater._download_and_extract("u", fetch=lambda url, **k: data)
    assert (out / "pyproject.toml").exists()


def test_rejects_path_traversal():
    data = zip_bytes({"../evil.bat": "x"})
    with pytest.raises(ValueError):
        updater._download_and_extract("u", fetch=lambda url, **k: data)


def test_copy_tree_keeps_venv_and_data(tmp_path):
    src, dst = tmp_path / "new", tmp_path / "app"
    (src / "src").mkdir(parents=True)
    (src / "src" / "a.py").write_text("new")
    (src / ".venv").mkdir()
    (src / ".venv" / "marker").write_text("from update")
    (dst / ".venv").mkdir(parents=True)
    (dst / ".venv" / "marker").write_text("mine")
    updater.copy_tree(src, dst)
    assert (dst / "src" / "a.py").read_text() == "new"
    assert (dst / ".venv" / "marker").read_text() == "mine"


def test_swap_script_waits_retries_and_restarts():
    s = updater.windows_swap_script(Path(r"C:\t\new"), Path(r"C:\apps\yt"), 4242)
    assert 'PID eq 4242' in s and "robocopy" in s and "goto copy" in s
    assert updater.APP_EXE in s and s.count("\r\n") > 10
