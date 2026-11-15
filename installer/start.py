"""Einstiegspunkt für das PyInstaller-Paket (LogistikMap.exe)."""

import multiprocessing
import sys

from logistikmap.__main__ import main

if __name__ == "__main__":
    multiprocessing.freeze_support()  # Arbeitsprozesse der Kachelerzeugung im PyInstaller-Paket
    sys.exit(main())
