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


# Standardwerte, in den Einstellungen änderbar
STANDARD_INAKTIV_STUNDEN = 12  # ohne Nutzung abgemeldet nach …
STANDARD_AD_STUNDEN = 12  # AD-Benutzer spätestens nach … neu anmelden (gesperrte Konten wirken so binnen einer Schicht)


def sitzungsdauer(db: Datenbank) -> tuple[float, float]:
    inaktiv = float(db.einstellung("sitzung_inaktiv_stunden", STANDARD_INAKTIV_STUNDEN) or STANDARD_INAKTIV_STUNDEN)
    ad = float(db.einstellung("sitzung_ad_stunden", STANDARD_AD_STUNDEN) or STANDARD_AD_STUNDEN)
    return inaktiv, ad


def benutzer_zur_sitzung(db: Datenbank, token: str | None) -> dict | None:
    if not token:
        return None
    th = _token_hash(token)
    inaktiv, ad = sitzungsdauer(db)
    row = db.eins(
        """SELECT b.id, b.benutzername, b.anzeigename, b.sprache, b.aktiv, b.quelle,
                  r.schluessel AS rolle, r.name AS rollenname, r.rechte
             FROM sitzungen s
             JOIN benutzer b ON b.id = s.benutzer_id
             JOIN rollen r ON r.id = b.rolle_id
            WHERE s.token_hash = ?
              AND s.zuletzt >= datetime('now', ?)
              AND s.erstellt >= datetime('now', CASE WHEN b.quelle = 'lokal' THEN ? ELSE ? END)""",
        (th, f"-{inaktiv * 60:.0f} minutes", f"-{SITZUNG_TAGE} days", f"-{ad * 60:.0f} minutes"),
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
    """Sperrt nach zu vielen Fehlversuchen für 60 Sekunden.

    Je Benutzername nach 5 Fehlversuchen. Je Adresse erst nach 30 – hinter Terminalservern
    oder Citrix teilen sich viele Personen eine Adresse, ein Vertipper soll nicht alle aussperren.
    """

    MAX_VERSUCHE = 5
    MAX_JE_ADRESSE = 30
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
                grenze = self.MAX_JE_ADRESSE if s.startswith("a:") else self.MAX_VERSUCHE
                if len(liste) >= grenze:
                    return True
        return False

    def fehlschlag(self, *schluessel: str) -> None:
        with self._sperre:
            if len(self._fehler) > 5000:
                # Vom Internet aus erreichbar: Bots probieren laufend neue Namen – alte Einträge
                # aufräumen, sonst wächst die Liste unbegrenzt.
                jetzt = time.monotonic()
                self._fehler = {k: v for k, v in self._fehler.items() if v and jetzt - v[-1] < self.SPERRZEIT}
            for s in schluessel:
                self._fehler.setdefault(s, []).append(time.monotonic())

    def erfolg(self, *schluessel: str) -> None:
        with self._sperre:
            for s in schluessel:
                self._fehler.pop(s, None)
