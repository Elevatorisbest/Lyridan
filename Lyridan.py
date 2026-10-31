"""Entry script (used by PyInstaller and for `python Lyridan.py`)."""
import multiprocessing
import sys

from lyridan.cli import main

if __name__ == "__main__":
    multiprocessing.freeze_support()
    sys.exit(main())
