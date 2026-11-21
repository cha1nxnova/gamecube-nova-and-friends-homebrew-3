"""Entry point for the packaged Pawtation.exe: opens the desktop app (and, on first run, the GameCube setup)."""
import sys

from pawtation import gui

if __name__ == "__main__":
    sys.exit(gui.run())
