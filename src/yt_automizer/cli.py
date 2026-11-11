"""Command line: `yt-automizer setup | doctor | auth | whoami | serve`."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys

from . import auth, config


def doctor() -> int:
    ok = True

    def line(good: bool, text: str, fix: str = "") -> None:
        nonlocal ok
        ok &= good
        print(f"  [{'OK' if good else 'X '}] {text}" + ("" if good or not fix else f"\n        -> {fix}"))

    print("Comprobando la instalación...")
    line(sys.version_info >= (3, 10), f"Python {sys.version.split()[0]}", "Instala Python 3.10 o superior")
    line(config.client_secret_path().exists(), "Clave de Google (client_secret.json)", "Ejecuta: yt-automizer setup")
    try:
        yt, an = auth.build_clients()
        from .config import load_settings
        from .service import YouTubeService

        info = YouTubeService(yt, an, load_settings()).channel_overview()
        line(True, f"Canal conectado: {info['title']}")
    except Exception as exc:
        line(False, f"Conexión con YouTube ({exc})", "Ejecuta: yt-automizer setup")
    claude = shutil.which("claude")
    if claude:
        res = subprocess.run([claude, "mcp", "get", "youtube"], capture_output=True, text=True)
        line(res.returncode == 0, "Servidor 'youtube' registrado en Claude Code", "Ejecuta: yt-automizer setup")
    else:
        line(False, "Comando 'claude' (Claude Code) no encontrado",
             "Instala Claude Code: https://claude.com/claude-code (o usa el .mcp.json de esta carpeta)")
    print("Todo bien." if ok else "Hay cosas por arreglar (mira las flechas).")
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="yt-automizer")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("setup", help="Instalación guiada (una sola vez)")
    s.add_argument("--redo", action="store_true", help="Repetir también los pasos de Google Cloud")
    sub.add_parser("doctor", help="Comprobar que todo está conectado")
    sub.add_parser("auth", help="Volver a iniciar sesión con Google")
    sub.add_parser("whoami", help="Ver qué canal está conectado")
    sub.add_parser("serve", help="Servidor MCP (Claude Code lo arranca solo)")
    args = p.parse_args(argv)

    if args.cmd == "setup":
        from .setup_wizard import run

        run(force=args.redo)
    elif args.cmd == "doctor":
        sys.exit(doctor())
    elif args.cmd == "auth":
        auth.run_login_flow()
        print(f"Sesión guardada en {config.token_path()}")
    elif args.cmd == "whoami":
        from .config import load_settings
        from .service import YouTubeService

        yt, an = auth.build_clients()
        print(json.dumps(YouTubeService(yt, an, load_settings()).channel_overview(), indent=2, ensure_ascii=False))
    elif args.cmd == "serve":
        from .server import main as serve

        serve()


if __name__ == "__main__":
    main()
