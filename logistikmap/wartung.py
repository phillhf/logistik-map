"""Sicherung, Wiederherstellung und Updates.

Eine Sicherung ist eine ZIP-Datei mit
  manifest.json   Version, Zeitpunkt
  logistikmap.db  Datenbank (konsistente Kopie)
  dokumente/      hochgeladene PDF-Pläne
Kartenkacheln werden nicht gesichert, sie werden nach einer Wiederherstellung neu erzeugt.

Updates: Prüft die GitHub-Releases. Das Setup wird geladen, per SHA-256 geprüft und über eine
einmalige geplante Aufgabe als SYSTEM gestartet. So läuft es unabhängig vom Dienst weiter,
den es während der Installation beendet und danach wieder startet.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
import zipfile
from datetime import datetime
from pathlib import Path

from . import __version__
from .config import Pfade

log = logging.getLogger(__name__)

REPO = "phillhf/logistik-map"
SETUP_MUSTER = re.compile(r"^LogistikMap-Setup-(\d+\.\d+\.\d+)\.exe$")
AUTO_PRAEFIX = "auto-"
UPDATE_AUFGABE = "LogistikMap Update"


class WartungsFehler(Exception):
    def __init__(self, code: str, **extra):
        super().__init__(code)
        self.code = code
        self.extra = extra


# --------------------------------------------------------------------------- Sicherung
def sicherung_erstellen(db, pfade: Pfade, ziel: Path) -> Path:
    with tempfile.TemporaryDirectory() as tmp:
        kopie = Path(tmp) / "logistikmap.db"
        db.sichern_nach(kopie)
        tmp_zip = ziel.with_suffix(".tmp")
        with zipfile.ZipFile(tmp_zip, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("manifest.json", json.dumps({"app": "logistik-map", "version": __version__, "zeit": datetime.now().isoformat(timespec="seconds")}))
            z.write(kopie, "logistikmap.db")
            for pdf in sorted(pfade.dokumente.glob("*.pdf")):
                z.write(pdf, f"dokumente/{pdf.name}", compress_type=zipfile.ZIP_STORED)
        tmp_zip.replace(ziel)
    return ziel


def sicherung_pruefen(datei: Path) -> dict:
    try:
        with zipfile.ZipFile(datei) as z:
            namen = set(z.namelist())
            if "manifest.json" not in namen or "logistikmap.db" not in namen:
                raise WartungsFehler("sicherung_ungueltig")
            manifest = json.loads(z.read("manifest.json"))
            if manifest.get("app") != "logistik-map":
                raise WartungsFehler("sicherung_ungueltig")
            for n in namen:
                if n.startswith("/") or ".." in Path(n).parts:
                    raise WartungsFehler("sicherung_ungueltig")
            return manifest
    except zipfile.BadZipFile as e:
        raise WartungsFehler("sicherung_ungueltig") from e


def wiederherstellen(db, pfade: Pfade, kacheldienst, datei: Path) -> dict:
    manifest = sicherung_pruefen(datei)
    with tempfile.TemporaryDirectory() as tmp:
        with zipfile.ZipFile(datei) as z:
            z.extractall(tmp)
        neue_db = Path(tmp) / "logistikmap.db"
        try:
            con = sqlite3.connect(neue_db)
            ok = con.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
            con.execute("SELECT version FROM schema_version").fetchone()
            con.close()
        except sqlite3.DatabaseError as e:
            raise WartungsFehler("sicherung_ungueltig") from e
        if not ok:
            raise WartungsFehler("sicherung_ungueltig")
        # vorher den aktuellen Stand sichern
        sicherung_erstellen(db, pfade, pfade.sicherungen / f"vor-wiederherstellung-{datetime.now():%Y%m%d-%H%M%S}.zip")
        kacheldienst.stoppen()
        db.ersetzen_durch(neue_db)
        for pdf in pfade.dokumente.glob("*"):
            pdf.unlink()
        quelle = Path(tmp) / "dokumente"
        if quelle.exists():
            for pdf in quelle.glob("*.pdf"):
                shutil.copy2(pdf, pfade.dokumente / pdf.name)
    shutil.rmtree(pfade.kacheln, ignore_errors=True)
    pfade.kacheln.mkdir(parents=True, exist_ok=True)
    db.ausfuehren("UPDATE plaene SET status = 'wartet', fortschritt = 0")
    kacheldienst.starten()
    return manifest


def sicherungen_liste(pfade: Pfade) -> list[dict]:
    return [
        {"name": p.name, "groesse": p.stat().st_size, "zeit": datetime.fromtimestamp(p.stat().st_mtime).isoformat(timespec="seconds")}
        for p in sorted(pfade.sicherungen.glob("*.zip"), key=lambda p: p.stat().st_mtime, reverse=True)
    ]


class AutoSicherung:
    """Legt täglich eine Sicherung an und behält die letzten `anzahl`."""

    def __init__(self, db, pfade: Pfade):
        self.db = db
        self.pfade = pfade
        self._stopp = threading.Event()
        self._thread: threading.Thread | None = None

    def starten(self) -> None:
        self._thread = threading.Thread(target=self._schleife, name="sicherung", daemon=True)
        self._thread.start()

    def stoppen(self) -> None:
        self._stopp.set()

    def jetzt_falls_faellig(self) -> Path | None:
        auto = sorted(self.pfade.sicherungen.glob(f"{AUTO_PRAEFIX}*.zip"))
        if auto and time.time() - auto[-1].stat().st_mtime < 23 * 3600:
            return None
        ziel = self.pfade.sicherungen / f"{AUTO_PRAEFIX}{datetime.now():%Y%m%d-%H%M%S}.zip"
        sicherung_erstellen(self.db, self.pfade, ziel)
        anzahl = int(self.db.einstellung("sicherung_anzahl", 14) or 14)
        auto = sorted(self.pfade.sicherungen.glob(f"{AUTO_PRAEFIX}*.zip"))
        for alt in auto[:-anzahl]:
            alt.unlink(missing_ok=True)
        log.info("Automatische Sicherung: %s", ziel.name)
        return ziel

    def _schleife(self) -> None:
        if self._stopp.wait(60):  # nicht direkt beim Start
            return
        while not self._stopp.is_set():
            try:
                self.jetzt_falls_faellig()
            except Exception:
                log.exception("Automatische Sicherung fehlgeschlagen")
            if self._stopp.wait(3600):
                return


# --------------------------------------------------------------------------- Updates
def version_tupel(v: str) -> tuple[int, ...]:
    return tuple(int(x) for x in re.findall(r"\d+", v)[:3])


_update_cache: dict = {"zeit": 0.0, "daten": None}


def update_pruefen(neu: bool = False, abrufen=None) -> dict:
    """Fragt das neueste Release bei GitHub ab (10 Minuten zwischengespeichert)."""
    if not neu and _update_cache["daten"] and time.time() - _update_cache["zeit"] < 600:
        return _update_cache["daten"]
    abrufen = abrufen or _github_json
    try:
        rel = abrufen(f"https://api.github.com/repos/{REPO}/releases/latest")
    except Exception as e:
        log.info("Update-Prüfung fehlgeschlagen: %s", e)
        return {"aktuell": __version__, "fehler": "keine_verbindung"}
    neueste = rel.get("tag_name", "").lstrip("v")
    setup = next((a for a in rel.get("assets", []) if SETUP_MUSTER.match(a["name"])), None)
    pruefsumme = next((a for a in rel.get("assets", []) if setup and a["name"] == setup["name"] + ".sha256"), None)
    daten = {
        "aktuell": __version__,
        "neueste": neueste,
        "verfuegbar": bool(neueste) and version_tupel(neueste) > version_tupel(__version__),
        "notizen": rel.get("body", ""),
        "url": rel.get("html_url", ""),
        "setup_url": setup["browser_download_url"] if setup else None,
        "sha256_url": pruefsumme["browser_download_url"] if pruefsumme else None,
        "installierbar": bool(setup and pruefsumme) and sys.platform == "win32" and getattr(sys, "frozen", False),
    }
    _update_cache.update(zeit=time.time(), daten=daten)
    return daten


def _github_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": "logistik-map-updater"})
    with urllib.request.urlopen(req, timeout=8) as r:
        return json.loads(r.read())


def _laden(url: str, ziel: Path) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": "logistik-map-updater"})
    with urllib.request.urlopen(req, timeout=60) as r, ziel.open("wb") as f:
        shutil.copyfileobj(r, f)


def update_installieren(pfade: Pfade, info: dict) -> str:
    if not info.get("installierbar"):
        raise WartungsFehler("update_nicht_moeglich")
    pfade.updates.mkdir(parents=True, exist_ok=True)
    name = info["setup_url"].rsplit("/", 1)[-1]
    if not SETUP_MUSTER.match(name):
        raise WartungsFehler("update_nicht_moeglich")
    setup = pfade.updates / name
    pruef = pfade.updates / (name + ".sha256")
    _laden(info["sha256_url"], pruef)
    _laden(info["setup_url"], setup)
    erwartet = pruef.read_text(encoding="ascii").split()[0].lower()
    h = hashlib.sha256()
    with setup.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    if h.hexdigest() != erwartet:
        setup.unlink(missing_ok=True)
        raise WartungsFehler("update_pruefsumme")
    befehl = f'"{setup}" /VERYSILENT /SUPPRESSMSGBOXES /NORESTART /LOG="{pfade.logs / "update.log"}"'
    schtasks = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "schtasks.exe"
    subprocess.run([str(schtasks), "/Create", "/F", "/TN", UPDATE_AUFGABE, "/SC", "ONCE", "/ST", "00:00", "/SD", "01/01/2099",
                    "/RU", "SYSTEM", "/RL", "HIGHEST", "/TR", befehl], check=True, capture_output=True)
    subprocess.run([str(schtasks), "/Run", "/TN", UPDATE_AUFGABE], check=True, capture_output=True)
    log.info("Update auf %s gestartet", info.get("neueste"))
    return info.get("neueste", "")


def neustart_planen(verzoegerung: float = 1.0) -> None:
    """Beendet den Prozess mit Fehlercode. Der Windows-Dienst (WinSW) startet ihn dann neu."""

    def ende():
        time.sleep(verzoegerung)
        log.info("Neustart angefordert")
        os._exit(3)

    threading.Thread(target=ende, daemon=True).start()
