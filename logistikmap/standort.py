"""Standorte: mehrere Krankenhäuser in einer Installation.

Der aktuelle Standort gilt für eine Anfrage und steht in einem Cookie. Die Middleware in
server.py setzt ihn zu Beginn jeder Anfrage; alle Listen, Berechnungen und Neuanlagen richten
sich danach. Außerhalb einer Anfrage (Tests, Hintergrund) gilt der erste Standort.
"""

from __future__ import annotations

import contextvars

COOKIE = "lm_standort"
# Tabellen, die direkt einem Standort gehören; alles darunter hängt über Fremdschlüssel daran
TABELLEN = ("gebaeudeteile", "dokumente", "aufzuege", "transportarten", "wagentypen", "lieferungen", "szenarien", "sondertage")
# Einstellungen, die je Standort gelten (gespeichert als „s<id>.<schlüssel>“)
ORT_EINSTELLUNGEN = ("bundesland", "bundesland_bestaetigt", "stammdaten_bestaetigt")

_aktuell: contextvars.ContextVar[int | None] = contextvars.ContextVar("standort", default=None)


def setzen(sid: int) -> contextvars.Token:
    return _aktuell.set(sid)


def aktuell(db) -> int:
    sid = _aktuell.get()
    if sid is not None:
        return sid
    erster = db.eins("SELECT id FROM standorte ORDER BY id LIMIT 1")
    return erster["id"] if erster else 1


def gueltig(db, wert: str | None) -> int:
    """Standort aus dem Cookie, falls es ihn gibt, sonst der erste."""
    try:
        sid = int(wert or 0)
    except ValueError:
        sid = 0
    if sid and db.eins("SELECT 1 FROM standorte WHERE id = ?", (sid,)):
        return sid
    erster = db.eins("SELECT id FROM standorte ORDER BY id LIMIT 1")
    return erster["id"] if erster else 1
