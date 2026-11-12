"""Setup logic shared by the desktop app and the `yt-automizer setup` command.

Opens each Google Cloud page, picks up the downloaded OAuth file from Downloads,
logs in, and registers the MCP server with Claude Code. Windows, macOS and Linux.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
import webbrowser
from dataclasses import dataclass
from pathlib import Path

from . import auth, config


@dataclass(frozen=True)
class GoogleStep:
    title: str
    text: str
    url: str


GOOGLE_STEPS = [
    GoogleStep(
        "Crear el proyecto",
        "Entra con la MISMA cuenta de Google de tu canal.\n"
        "Nombre del proyecto: yt-automizer. Pulsa «Crear».",
        "https://console.cloud.google.com/projectcreate",
    ),
    GoogleStep(
        "Activar las APIs de YouTube",
        "Comprueba que arriba aparece el proyecto yt-automizer y pulsa «Habilitar».",
        "https://console.cloud.google.com/apis/enableflow?apiid=youtube.googleapis.com,youtubeanalytics.googleapis.com",
    ),
    GoogleStep(
        "Pantalla de permisos",
        "Pulsa «Comenzar». Nombre de la app: yt-automizer. Pon tu correo.\n"
        "Público: «Externo». Acepta y crea.",
        "https://console.cloud.google.com/auth/branding",
    ),
    GoogleStep(
        "Publicar la app",
        "En «Público» pulsa «Publicar app» y confirma.\n"
        "Así el inicio de sesión no caduca cada 7 días.",
        "https://console.cloud.google.com/auth/audience",
    ),
    GoogleStep(
        "Descargar la clave",
        "Tipo de aplicación: «App de escritorio». Nombre: yt-automizer. Pulsa «Crear».\n"
        "En la ventana que aparece pulsa «Descargar JSON».\n"
        "La app detecta el archivo sola en tu carpeta de Descargas.",
        "https://console.cloud.google.com/auth/clients/create",
    ),
]

LOGIN_HINT = (
    "Se abrirá Google: elige la cuenta (y el canal) de YouTube y marca todas las casillas.\n"
    "Si aparece «Google no ha verificado esta aplicación», es normal: es tu propia app.\n"
    "Pulsa «Configuración avanzada» → «Ir a yt-automizer»."
)


# --------------------------------------------------------------- client secret
def is_client_secret(path: Path) -> bool:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return isinstance(data, dict) and "client_id" in data.get("installed", {})


def downloads_folders() -> list[Path]:
    home = Path.home()
    return [home / "Downloads", home / "Descargas", home / "OneDrive" / "Downloads",
            home / "Desktop", home / "Escritorio"]


def find_downloaded_secret(folders: list[Path], since: float) -> Path | None:
    """Newest Google OAuth desktop-client JSON modified after ``since`` in any of ``folders``."""
    found = []
    for folder in folders:
        if folder.is_dir():
            for p in folder.glob("client_secret*.json"):
                if p.stat().st_mtime >= since and is_client_secret(p):
                    found.append(p)
    return max(found, key=lambda p: p.stat().st_mtime) if found else None


def install_secret(src: Path) -> Path:
    if not is_client_secret(src):
        raise ValueError("Ese archivo no es una clave de tipo «App de escritorio».")
    dst = config.client_secret_path()
    shutil.copyfile(src, dst)
    return dst


def has_secret() -> bool:
    return config.client_secret_path().exists()


# ----------------------------------------------------------- login + channel
def connect_channel() -> dict:
    """Open the Google login in the browser and return the channel overview."""
    auth.run_login_flow(timeout_seconds=600)
    return channel_info()


def channel_info(allow_browser_login: bool = True) -> dict:
    from .config import load_settings
    from .service import YouTubeService

    yt, an = auth.build_clients(allow_browser_login)
    return YouTubeService(yt, an, load_settings()).channel_overview()


def disconnect() -> None:
    config.token_path().unlink(missing_ok=True)


# --------------------------------------------------------------- Claude Code
def mcp_command() -> list[str]:
    """How Claude Code should start the server on this PC."""
    if getattr(sys, "frozen", False):  # packaged app: server exe sits next to the app exe
        exe = "yt-automizer-server.exe" if os.name == "nt" else "yt-automizer-server"
        return [str(Path(sys.executable).with_name(exe))]
    return [sys.executable, "-m", "yt_automizer", "serve"]


def find_claude() -> str | None:
    found = shutil.which("claude")
    if found:
        return found
    # Common install locations when PATH isn't refreshed yet (GUI apps on Windows).
    home = Path.home()
    for p in [home / ".local" / "bin" / "claude.exe", home / ".local" / "bin" / "claude",
              home / "AppData" / "Roaming" / "npm" / "claude.cmd"]:
        if p.exists():
            return str(p)
    return None


def _run_hidden(args: list[str]) -> subprocess.CompletedProcess:
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return subprocess.run(args, capture_output=True, text=True, creationflags=flags)


def is_registered() -> bool:
    claude = find_claude()
    if not claude:
        return False
    return _run_hidden([claude, "mcp", "get", "youtube"]).returncode == 0


def register_with_claude_code() -> tuple[bool, str]:
    cmd = mcp_command()
    claude = find_claude()
    if claude:
        _run_hidden([claude, "mcp", "remove", "--scope", "user", "youtube"])
        res = _run_hidden([claude, "mcp", "add", "--scope", "user", "youtube", "--", *cmd])
        if res.returncode == 0:
            return True, "Claude Code tiene el servidor «youtube» en cualquier carpeta."
        reason = (res.stderr or res.stdout).strip()
        return False, f"No se pudo registrar en Claude Code: {reason}"
    target = config.home_dir() / "mcp.json"
    target.write_text(json.dumps({"mcpServers": {"youtube": {"command": cmd[0], "args": cmd[1:]}}}, indent=2))
    return False, ("No encuentro Claude Code en este PC. Instálalo desde claude.com/claude-code "
                   "y pulsa «Conectar con Claude Code» otra vez.")


# ------------------------------------------------------------------ terminal
def run(force: bool = False) -> None:
    """Text version of the same steps, for `yt-automizer setup`."""
    print("Configuración de YouTube AI-utomizer (solo una vez, unos 5 minutos)")
    config.save_default_settings()
    if has_secret() and not force:
        print(f"Ya tienes la clave de Google en {config.client_secret_path()}.")
    else:
        started = time.time()
        for i, step in enumerate(GOOGLE_STEPS, 1):
            print(f"\n=== Paso {i}/{len(GOOGLE_STEPS)}: {step.title} ===\n{step.text}")
            webbrowser.open(step.url)
            if i < len(GOOGLE_STEPS):
                _input("Cuando termines, pulsa Enter...")
        print("\nBuscando el archivo en Descargas (o arrástralo aquí y pulsa Enter)...")
        while True:
            found = find_downloaded_secret(downloads_folders(), started)
            if found:
                break
            typed = _input("").strip('"').strip("'")
            if typed and is_client_secret(Path(typed).expanduser()):
                found = Path(typed).expanduser()
                break
            time.sleep(3)
        print(f"Clave guardada en {install_secret(found)}")

    print("\n=== Conectar tu canal ===\n" + LOGIN_HINT)
    info = connect_channel()
    print(f"Canal conectado: {info['title']} ({info['subscribers']} suscriptores)")
    print(register_with_claude_code()[1])
    print("\nListo. Abre Claude Code y escribe: «Haz la revisión semanal de mi canal».")


def _input(msg: str) -> str:
    try:
        return input(msg)
    except EOFError:
        return ""
