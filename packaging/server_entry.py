"""PyInstaller entry for the console MCP server that Claude Code launches.

No arguments = run the MCP server. Other commands work too: doctor, whoami, auth.
"""
import sys

from yt_automizer.cli import main

main(sys.argv[1:] or ["serve"])
