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
# Standorte, die der angemeldete Benutzer sehen darf; None = alle (Administratoren und alle ohne Zuordnung)
_erlaubt: contextvars.ContextVar[frozenset[int] | None] = contextvars.ContextVar("standorte_erlaubt", default=None)

# Wie ein Objekt zu seinem Standort kommt (für die Prüfung „darf dieser Benutzer das sehen?“)
_STANDORT_SQL = {
    **{t: f"SELECT standort_id AS s FROM {t} WHERE id = ?" for t in TABELLEN},
    "stockwerke": "SELECT g.standort_id AS s FROM stockwerke x JOIN gebaeudeteile g ON g.id = x.gebaeudeteil_id WHERE x.id = ?",
    **{t: f"""SELECT g.standort_id AS s FROM {t} x JOIN stockwerke w ON w.id = x.stockwerk_id
                JOIN gebaeudeteile g ON g.id = w.gebaeudeteil_id WHERE x.id = ?""" for t in ("knoten", "kanten", "flaechen")},
    "plaene": "SELECT d.standort_id AS s FROM plaene x JOIN dokumente d ON d.id = x.dokument_id WHERE x.id = ?",
}


def setzen(sid: int) -> contextvars.Token:
    return _aktuell.set(sid)


def aktuell(db) -> int:
    sid = _aktuell.get()
    if sid is not None:
        return sid
    erster = db.eins("SELECT id FROM standorte ORDER BY id LIMIT 1")
    return erster["id"] if erster else 1


def gueltig(db, wert: str | None, erlaubt: frozenset[int] | None = None) -> int:
    """Standort aus dem Cookie, falls es ihn gibt (und der Benutzer ihn sehen darf), sonst der erste erlaubte."""
    try:
        sid = int(wert or 0)
    except ValueError:
        sid = 0
    if sid and (erlaubt is None or sid in erlaubt) and db.eins("SELECT 1 FROM standorte WHERE id = ?", (sid,)):
        return sid
    if erlaubt is not None:
        erster = db.eins(f"SELECT id FROM standorte WHERE id IN ({','.join('?' * len(erlaubt))}) ORDER BY id LIMIT 1", tuple(erlaubt)) if erlaubt else None
        return erster["id"] if erster else 0  # 0: kein Standort – Listen bleiben leer
    erster = db.eins("SELECT id FROM standorte ORDER BY id LIMIT 1")
    return erster["id"] if erster else 1


def erlaubte_fuer(db, token_hash: str | None) -> frozenset[int] | None:
    """Erlaubte Standorte zur Sitzung. None = alle: Administratoren, Benutzer ohne Zuordnung, nicht angemeldet."""
    if not token_hash:
        return None
    b = db.eins(
        """SELECT b.id, r.rechte FROM sitzungen s JOIN benutzer b ON b.id = s.benutzer_id
             JOIN rollen r ON r.id = b.rolle_id WHERE s.token_hash = ?""",
        (token_hash,),
    )
    if b is None or '"verwalten"' in b["rechte"]:
        return None
    ids = [r["standort_id"] for r in db.alle("SELECT standort_id FROM benutzer_standorte WHERE benutzer_id = ?", (b["id"],))]
    return frozenset(ids) if ids else None


def erlaubt_setzen(werte: frozenset[int] | None) -> contextvars.Token:
    return _erlaubt.set(werte)


def erlaubt() -> frozenset[int] | None:
    return _erlaubt.get()


def darf(db, tabelle: str, rid: int) -> bool:
    """Gehört das Objekt zu einem Standort, den der aktuelle Benutzer sehen darf?"""
    werte = _erlaubt.get()
    sql = _STANDORT_SQL.get(tabelle)
    if werte is None or sql is None:
        return True
    row = db.eins(sql, (rid,))
    return row is None or row["s"] in werte  # nicht vorhanden: die Stelle selbst meldet 404
