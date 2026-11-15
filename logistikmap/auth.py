"""Passwörter, Sitzungen und Rechte."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import threading
import time

from .db import Datenbank

SITZUNG_COOKIE = "lm_sitzung"
SITZUNG_TAGE = 14
MIN_PASSWORT = 8

_SCRYPT = {"n": 2**14, "r": 8, "p": 1, "dklen": 32}


def passwort_hash(passwort: str) -> str:
    salz = secrets.token_bytes(16)
    h = hashlib.scrypt(passwort.encode("utf-8"), salt=salz, maxmem=64 * 1024 * 1024, **_SCRYPT)
    return "scrypt$" + base64.b64encode(salz).decode() + "$" + base64.b64encode(h).decode()


def passwort_pruefen(passwort: str, gespeichert: str) -> bool:
    try:
        art, salz_b64, h_b64 = gespeichert.split("$")
    except ValueError:
        return False
    if art != "scrypt":
        return False
    salz = base64.b64decode(salz_b64)
    h = hashlib.scrypt(passwort.encode("utf-8"), salt=salz, maxmem=64 * 1024 * 1024, **_SCRYPT)
    return hmac.compare_digest(h, base64.b64decode(h_b64))


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def sitzung_anlegen(db: Datenbank, benutzer_id: int) -> str:
    token = secrets.token_urlsafe(32)
    db.ausfuehren("INSERT INTO sitzungen (token_hash, benutzer_id) VALUES (?, ?)", (_token_hash(token), benutzer_id))
    return token


def sitzung_beenden(db: Datenbank, token: str) -> None:
    db.ausfuehren("DELETE FROM sitzungen WHERE token_hash = ?", (_token_hash(token),))


def benutzer_zur_sitzung(db: Datenbank, token: str | None) -> dict | None:
    if not token:
        return None
    th = _token_hash(token)
    row = db.eins(
        """SELECT b.id, b.benutzername, b.anzeigename, b.sprache, b.aktiv,
                  r.schluessel AS rolle, r.name AS rollenname, r.rechte
             FROM sitzungen s
             JOIN benutzer b ON b.id = s.benutzer_id
             JOIN rollen r ON r.id = b.rolle_id
            WHERE s.token_hash = ?
              AND s.zuletzt >= datetime('now', ?)""",
        (th, f"-{SITZUNG_TAGE} days"),
    )
    if not row or not row["aktiv"]:
        return None
    db.ausfuehren("UPDATE sitzungen SET zuletzt = datetime('now') WHERE token_hash = ?", (th,))
    row["rechte"] = json.loads(row["rechte"])
    del row["aktiv"]
    return row


def alte_sitzungen_loeschen(db: Datenbank) -> None:
    db.ausfuehren("DELETE FROM sitzungen WHERE zuletzt < datetime('now', ?)", (f"-{SITZUNG_TAGE} days",))


class Anmeldebremse:
    """Nach 5 Fehlversuchen für einen Benutzernamen oder eine Adresse 60 Sekunden sperren."""

    MAX_VERSUCHE = 5
    SPERRZEIT = 60.0

    def __init__(self) -> None:
        self._fehler: dict[str, list[float]] = {}
        self._sperre = threading.Lock()

    def gesperrt(self, *schluessel: str) -> bool:
        jetzt = time.monotonic()
        with self._sperre:
            for s in schluessel:
                liste = [t for t in self._fehler.get(s, []) if jetzt - t < self.SPERRZEIT]
                self._fehler[s] = liste
                if len(liste) >= self.MAX_VERSUCHE:
                    return True
        return False

    def fehlschlag(self, *schluessel: str) -> None:
        with self._sperre:
            for s in schluessel:
                self._fehler.setdefault(s, []).append(time.monotonic())

    def erfolg(self, *schluessel: str) -> None:
        with self._sperre:
            for s in schluessel:
                self._fehler.pop(s, None)
