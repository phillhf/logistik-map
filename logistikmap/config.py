"""Datenordner und config.json.

Der Datenordner enthält Datenbank, hochgeladene PDFs, Kartenkacheln und Protokolle.
Reihenfolge: --data, Umgebungsvariable LOGISTIKMAP_DATA, sonst
  installiert (PyInstaller): C:\\ProgramData\\Logistik Map
  aus dem Quellcode:          <Projekt>\\data
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

STANDARD_PORT = 8470


def standard_datenordner() -> Path:
    env = os.environ.get("LOGISTIKMAP_DATA")
    if env:
        return Path(env)
    if getattr(sys, "frozen", False):
        base = os.environ.get("PROGRAMDATA", r"C:\ProgramData")
        return Path(base) / "Logistik Map"
    return Path(__file__).resolve().parent.parent / "data"


@dataclass
class Konfiguration:
    port: int = STANDARD_PORT
    host: str = "0.0.0.0"
    zertifikat: str = ""  # HTTPS: Pfad zur Zertifikatsdatei (PEM), leer = HTTP
    schluessel: str = ""  # HTTPS: Pfad zum privaten Schlüssel (PEM)

    @property
    def https(self) -> bool:
        return bool(self.zertifikat and self.schluessel)


class Pfade:
    def __init__(self, datenordner: Path):
        self.daten = Path(datenordner)
        self.datenbank = self.daten / "logistikmap.db"
        self.dokumente = self.daten / "dokumente"
        self.kacheln = self.daten / "kacheln"
        self.logs = self.daten / "logs"
        self.config = self.daten / "config.json"
        self.sicherungen = self.daten / "sicherungen"
        self.updates = self.daten / "updates"

    def anlegen(self) -> None:
        for p in (self.daten, self.dokumente, self.kacheln, self.logs, self.sicherungen):
            p.mkdir(parents=True, exist_ok=True)


def lade_konfiguration(pfade: Pfade) -> Konfiguration:
    k = Konfiguration()
    if pfade.config.exists():
        try:
            daten = json.loads(pfade.config.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            daten = {}
        if isinstance(daten.get("port"), int) and 1 <= daten["port"] <= 65535:
            k.port = daten["port"]
        if isinstance(daten.get("host"), str) and daten["host"]:
            k.host = daten["host"]
        for feld in ("zertifikat", "schluessel"):
            if isinstance(daten.get(feld), str):
                setattr(k, feld, daten[feld])
    return k


def speichere_konfiguration(pfade: Pfade, k: Konfiguration) -> None:
    pfade.daten.mkdir(parents=True, exist_ok=True)
    pfade.config.write_text(json.dumps(asdict(k), indent=2), encoding="utf-8")


def static_ordner() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "static"  # type: ignore[attr-defined]
    return Path(__file__).resolve().parent / "static"
