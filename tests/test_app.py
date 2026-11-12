"""The window builds and shows the right state. Skipped where Tk or a display is missing."""
import os
import sys

import pytest

tk = pytest.importorskip("tkinter")


@pytest.fixture
def root(tmp_path, monkeypatch):
    monkeypatch.setenv("YT_AUTOMIZER_HOME", str(tmp_path))
    if sys.platform.startswith("linux") and not os.environ.get("DISPLAY"):
        pytest.skip("no display")
    r = tk.Tk()
    yield r
    r.destroy()


def test_fresh_pc_shows_setup(root, monkeypatch):
    from yt_automizer import app, setup_wizard as sw, updater

    monkeypatch.setattr(sw, "is_registered", lambda: False)
    monkeypatch.setattr(sw, "find_claude", lambda: None)
    monkeypatch.setattr(updater, "check", lambda: updater.UpdateInfo("0.2.0", "0.2.0", False, "", "u", None, None))
    a = app.App(root)
    a._show_status(a._collect_status())
    assert a.main_btn.cget("text") == "Configurar todo"
    assert "no está instalado" in a.rows["claude"]["detail"].cget("text")
