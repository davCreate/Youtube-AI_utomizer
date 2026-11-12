"""Check GitHub Releases for a newer version and install it.

* Packaged app (.exe): downloads the release zip and swaps the files with a small
  script once the app has closed (a running .exe cannot overwrite itself on Windows).
* Source install (instalar.bat): downloads the release source, copies it over this
  folder (keeping .venv and your data) and reinstalls dependencies.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path

from . import __version__

GITHUB_REPO = os.environ.get("YT_AUTOMIZER_REPO", "davCreate/Youtube-AI_utomizer")
RELEASES_PAGE = f"https://github.com/{GITHUB_REPO}/releases"
API_LATEST = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
WINDOWS_ASSET = "YouTube-AI-utomizer-windows.zip"
APP_EXE = "YouTube-AI-utomizer.exe"
_KEEP = {".venv", ".git", ".mcp.json", ".yt-automizer"}


@dataclass
class UpdateInfo:
    current: str
    latest: str
    available: bool
    notes: str
    page_url: str
    asset_url: str | None  # packaged app zip
    source_url: str | None  # source zip


def parse_version(tag: str) -> tuple[int, ...]:
    nums = re.findall(r"\d+", tag.split("-")[0])
    return tuple(int(n) for n in nums[:3]) or (0,)


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def app_dir() -> Path:
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def _get(url: str, timeout: float = 15) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "yt-automizer-updater",
                                               "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def check(current: str = __version__, fetch=_get) -> UpdateInfo:
    """Raises on network errors; a repo with no releases yet reports 'no update'."""
    try:
        data = json.loads(fetch(API_LATEST))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return UpdateInfo(current, current, False, "Todavía no hay versiones publicadas.", RELEASES_PAGE, None, None)
        raise
    latest = data.get("tag_name", "0").lstrip("v")
    asset = next((a["browser_download_url"] for a in data.get("assets", []) if a.get("name") == WINDOWS_ASSET), None)
    return UpdateInfo(
        current=current,
        latest=latest,
        available=parse_version(latest) > parse_version(current),
        notes=(data.get("body") or "").strip(),
        page_url=data.get("html_url") or RELEASES_PAGE,
        asset_url=asset,
        source_url=data.get("zipball_url"),
    )


def _download_and_extract(url: str, fetch=_get) -> Path:
    tmp = Path(tempfile.mkdtemp(prefix="yt-automizer-update-"))
    archive = tmp / "update.zip"
    archive.write_bytes(fetch(url, timeout=300))
    out = tmp / "new"
    with zipfile.ZipFile(archive) as z:
        for name in z.namelist():  # refuse paths that escape the folder
            if name.startswith("/") or ".." in Path(name).parts:
                raise ValueError(f"Archivo sospechoso en la actualización: {name}")
        z.extractall(out)
    entries = list(out.iterdir())
    # GitHub source zips wrap everything in one top-level folder.
    return entries[0] if len(entries) == 1 and entries[0].is_dir() else out


def windows_swap_script(new_dir: Path, target: Path, pid: int) -> str:
    return "\r\n".join([
        "@echo off",
        "title Actualizando YouTube AI-utomizer",
        ":wait",
        f'tasklist /FI "PID eq {pid}" | find "{pid}" >nul && (timeout /t 1 /nobreak >nul & goto wait)',
        "set tries=0",
        ":copy",
        f'robocopy "{new_dir}" "{target}" /E /NFL /NDL /NJH /NJS /NP >nul',
        "if not errorlevel 8 goto done",
        "set /a tries+=1",
        "if %tries% GEQ 30 goto done",
        "echo Cierra Claude Code para terminar la actualizacion...",
        "timeout /t 2 /nobreak >nul",
        "goto copy",
        ":done",
        f'start "" "{target / APP_EXE}"',
        '(goto) 2>nul & del "%~f0"',
        "",
    ])


def install(info: UpdateInfo, fetch=_get) -> str:
    """Install the update. Returns 'restart' if the caller must quit now so the swap can run."""
    if is_frozen():
        if os.name != "nt" or not info.asset_url:
            raise RuntimeError("Descarga la nueva versión desde la página de releases.")
        new_dir = _download_and_extract(info.asset_url, fetch)
        script = new_dir.parent / "swap.bat"
        script.write_text(windows_swap_script(new_dir, app_dir(), os.getpid()), encoding="utf-8")
        subprocess.Popen(["cmd", "/c", str(script)], creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return "restart"

    if not info.source_url:
        raise RuntimeError("La versión publicada no tiene código fuente descargable.")
    new_dir = _download_and_extract(info.source_url, fetch)
    if not (new_dir / "pyproject.toml").exists() or not (new_dir / "src" / "yt_automizer").is_dir():
        raise RuntimeError("La descarga no parece una versión válida de la app.")
    copy_tree(new_dir, app_dir())
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    subprocess.run([sys.executable, "-m", "pip", "install", "--quiet", "-e", str(app_dir())],
                   check=True, creationflags=flags)
    return "restart"


def copy_tree(src: Path, dst: Path) -> None:
    for item in src.iterdir():
        if item.name in _KEEP:
            continue
        target = dst / item.name
        if item.is_dir():
            shutil.copytree(item, target, dirs_exist_ok=True)
        else:
            shutil.copy2(item, target)


def relaunch() -> None:
    if is_frozen():
        return  # the swap script starts the new version
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    python = sys.executable
    if os.name == "nt" and python.lower().endswith("python.exe"):
        python = python[:-10] + "pythonw.exe"
    subprocess.Popen([python, "-m", "yt_automizer.app"], creationflags=flags)
