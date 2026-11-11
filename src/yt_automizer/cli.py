"""Command line: `yt-automizer auth | whoami | serve`."""

from __future__ import annotations

import argparse
import json

from . import auth, config


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="yt-automizer")
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("auth", help="Log in with Google and save a token (run once)")
    a.add_argument("--no-browser", action="store_true", help="Print the URL instead of opening a browser")
    sub.add_parser("whoami", help="Show the connected channel")
    sub.add_parser("serve", help="Run the MCP server on stdio (Claude Code starts this for you)")
    args = p.parse_args(argv)

    if args.cmd == "auth":
        config.save_default_settings()
        auth.run_login_flow(open_browser=not args.no_browser)
        print(f"Saved login to {config.token_path()}")
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
