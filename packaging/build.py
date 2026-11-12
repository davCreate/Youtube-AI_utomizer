"""Build the desktop app and the MCP server as standalone executables.

    python packaging/build.py      ->  dist/YouTube-AI-utomizer/  (+ zip on Windows)
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
OUT = DIST / "YouTube-AI-utomizer"
COMMON = ["--noconfirm", "--onefile", "--clean", "--paths", str(ROOT / "src"),
          "--collect-data", "googleapiclient", "--collect-submodules", "mcp.server",
          "--exclude-module", "mcp.cli",
          "--hidden-import", "yt_automizer.server", "--distpath", str(OUT),
          "--workpath", str(ROOT / "build"), "--specpath", str(ROOT / "build")]


def pyinstaller(*args: str) -> None:
    subprocess.run([sys.executable, "-m", "PyInstaller", *COMMON, *args], check=True)


def main() -> None:
    shutil.rmtree(OUT, ignore_errors=True)
    pyinstaller("--windowed", "--name", "YouTube-AI-utomizer", str(ROOT / "packaging" / "app_entry.py"))
    pyinstaller("--console", "--name", "yt-automizer-server", str(ROOT / "packaging" / "server_entry.py"))
    shutil.copy(ROOT / "packaging" / "LEEME.txt", OUT / "LEEME.txt")
    if os.name == "nt":
        archive = shutil.make_archive(str(DIST / "YouTube-AI-utomizer-windows"), "zip", OUT)
        print(f"Built {archive}")
    print(f"Built {OUT}")


if __name__ == "__main__":
    main()
