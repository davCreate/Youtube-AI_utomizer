"""Guided PC setup: `yt-automizer setup`.

Opens each Google Cloud page in the browser, picks up the downloaded OAuth file from
the Downloads folder on its own, logs in, and registers the server with Claude Code.
Works on Windows, macOS and Linux.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

from . import auth, config

URL_NEW_PROJECT = "https://console.cloud.google.com/projectcreate"
URL_ENABLE_APIS = ("https://console.cloud.google.com/apis/enableflow"
                   "?apiid=youtube.googleapis.com,youtubeanalytics.googleapis.com")
URL_BRANDING = "https://console.cloud.google.com/auth/branding"
URL_AUDIENCE = "https://console.cloud.google.com/auth/audience"
URL_NEW_CLIENT = "https://console.cloud.google.com/auth/clients/create"


def _step(n: int, total: int, title: str) -> None:
    print(f"\n=== Paso {n}/{total}: {title} ===")


def _wait(msg: str = "Cuando termines, pulsa Enter para seguir...") -> str:
    try:
        return input(f"  {msg} ").strip()
    except EOFError:
        return ""


def _open(url: str) -> None:
    print(f"  Abriendo: {url}")
    webbrowser.open(url)


def is_client_secret(path: Path) -> bool:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return isinstance(data, dict) and "client_id" in data.get("installed", {})


def find_downloaded_secret(folders: list[Path], since: float) -> Path | None:
    """Newest Google OAuth desktop-client JSON modified after ``since`` in any of ``folders``."""
    found = []
    for folder in folders:
        if folder.is_dir():
            for p in folder.glob("client_secret*.json"):
                if p.stat().st_mtime >= since and is_client_secret(p):
                    found.append(p)
    return max(found, key=lambda p: p.stat().st_mtime) if found else None


def _downloads_folders() -> list[Path]:
    home = Path.home()
    return [home / "Downloads", home / "Descargas", home / "OneDrive" / "Downloads", home / "Desktop", home / "Escritorio"]


def _get_client_secret(started: float) -> Path:
    print("  Buscando el archivo en tu carpeta de Descargas (o arrástralo a esta ventana y pulsa Enter)...")
    deadline = time.time() + 15 * 60
    while time.time() < deadline:
        found = find_downloaded_secret(_downloads_folders(), started)
        if found:
            print(f"  Encontrado: {found}")
            return found
        typed = _wait("¿No lo encuentra? Arrastra aquí el .json y pulsa Enter (o solo Enter para volver a buscar):")
        if typed:
            p = Path(typed.strip('"').strip("'")).expanduser()
            if is_client_secret(p):
                return p
            print("  Ese archivo no es un cliente OAuth de tipo 'App de escritorio'. Prueba otra vez.")
        else:
            time.sleep(3)
    raise SystemExit("No he encontrado el archivo. Ejecuta de nuevo: yt-automizer setup")


def mcp_command() -> list[str]:
    """How Claude Code should start the server: this exact Python, so no PATH problems."""
    return [sys.executable, "-m", "yt_automizer", "serve"]


def register_with_claude_code() -> bool:
    claude = shutil.which("claude")
    cmd = mcp_command()
    if claude:
        subprocess.run([claude, "mcp", "remove", "--scope", "user", "youtube"], capture_output=True)
        res = subprocess.run([claude, "mcp", "add", "--scope", "user", "youtube", "--", *cmd],
                             capture_output=True, text=True)
        if res.returncode == 0:
            print("  Listo: Claude Code tendrá el servidor 'youtube' en cualquier carpeta.")
            return True
        print(f"  'claude mcp add' falló: {res.stderr.strip() or res.stdout.strip()}")
    # Fallback: project file next to the repo (gitignored), works when Claude Code is opened here.
    project_root = Path(__file__).resolve().parents[2]
    target = project_root / ".mcp.json"
    target.write_text(json.dumps({"mcpServers": {"youtube": {"command": cmd[0], "args": cmd[1:]}}}, indent=2))
    print(f"  No encontré el comando 'claude'. He creado {target}.")
    print("  Abre Claude Code dentro de esta carpeta y acepta el servidor 'youtube' cuando te pregunte.")
    return False


def run(force: bool = False) -> None:
    total = 4
    print("Configuración de YouTube AI-utomizer para Claude Code")
    print("Solo hay que hacerlo una vez. Tardarás unos 5 minutos.")
    config.save_default_settings()
    secret_dst = config.client_secret_path()

    if secret_dst.exists() and not force:
        print(f"\nYa tienes la clave de Google en {secret_dst}. Me salto los pasos de Google Cloud.")
    else:
        started = time.time()
        _step(1, total, "Crear el proyecto en Google Cloud")
        print("  Entra con la MISMA cuenta de Google de tu canal. Nombre del proyecto: yt-automizer. Pulsa 'Crear'.")
        _open(URL_NEW_PROJECT)
        _wait()

        print("\n  Ahora activa las dos APIs de YouTube: comprueba que arriba sale el proyecto yt-automizer y pulsa 'Habilitar'.")
        _open(URL_ENABLE_APIS)
        _wait()

        _step(2, total, "Pantalla de permisos")
        print("  Pulsa 'Comenzar'. Nombre de la app: yt-automizer. Pon tu correo. Público: 'Externo'. Acepta y crea.")
        _open(URL_BRANDING)
        _wait()
        print("\n  En 'Público' pulsa 'Publicar app' y confirma. Así el login no caduca cada 7 días.")
        print("  (Alternativa: deja 'Prueba' y añade tu correo en 'Usuarios de prueba'.)")
        _open(URL_AUDIENCE)
        _wait()

        _step(3, total, "Descargar la clave")
        print("  Tipo de aplicación: 'App de escritorio'. Nombre: yt-automizer. Pulsa 'Crear'.")
        print("  En la ventana que sale pulsa 'Descargar JSON'.")
        _open(URL_NEW_CLIENT)
        src = _get_client_secret(started)
        shutil.copyfile(src, secret_dst)
        print(f"  Guardada en {secret_dst}")

    _step(4, total, "Conectar tu canal y Claude Code")
    print("  Se abrirá Google: elige la cuenta (y el canal) de YouTube.")
    print("  Si sale 'Google no ha verificado esta aplicación': es tu propia app. Pulsa 'Configuración avanzada' -> 'Ir a yt-automizer'.")
    print("  Marca todas las casillas de permisos.")
    auth.run_login_flow()

    from .config import load_settings
    from .service import YouTubeService

    yt, an = auth.build_clients()
    info = YouTubeService(yt, an, load_settings()).channel_overview()
    print(f"  Canal conectado: {info['title']} ({info['subscribers']} suscriptores)")
    register_with_claude_code()

    print("\nTodo listo. Abre Claude Code y escribe por ejemplo:")
    print('  "Haz la revisión semanal de mi canal"')
    print('  "Encuéntrame un nicho: F1, aerodinámica, coches deportivos"')
    print("Si algo falla más adelante: yt-automizer doctor")
