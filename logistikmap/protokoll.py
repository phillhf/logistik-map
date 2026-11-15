"""Änderungsprotokoll: wer hat wann was angelegt, geändert oder gelöscht.

Eine Middleware schreibt jede erfolgreiche schreibende Anfrage an /api/ mit. Die Bezeichnung
des Objekts (z. B. Name der Lieferung) wird beim Löschen vorher, sonst nachher nachgeschlagen.
"""

from __future__ import annotations

import json
import logging
import re

from fastapi import Depends, FastAPI, Request
from starlette.responses import Response

from . import auth

log = logging.getLogger(__name__)

# Pfadanfang → (Tabelle, Spalte für die Bezeichnung)
OBJEKTE = {
    "lieferungen": ("lieferungen", "name"),
    "knoten": ("knoten", "name"),
    "kanten": ("kanten", "name"),
    "flaechen": ("flaechen", "name"),
    "stockwerke": ("stockwerke", "name"),
    "gebaeudeteile": ("gebaeudeteile", "name"),
    "dokumente": ("dokumente", "dateiname"),
    "benutzer": ("benutzer", "benutzername"),
    "rollen": ("rollen", "name"),
    "transportarten": ("transportarten", "name"),
    "wagentypen": ("wagentypen", "name"),
    "aufzuege": ("aufzuege", "name"),
    "szenarien": ("szenarien", "name"),
    "sondertage": ("sondertage", "name"),
    "plaene": ("plaene", "id"),
}
NICHT_PROTOKOLLIEREN = {"/api/anmelden", "/api/abmelden", "/api/ersteinrichtung", "/api/ich", "/api/einstellungen/ldap/test"}
PFAD = re.compile(r"^/api/([a-z_]+)(?:/(\d+))?(?:/([a-z_/]+))?")


def _bezeichnung(db, objekt: str, oid: int | None) -> str:
    if oid is None or objekt not in OBJEKTE:
        return ""
    tabelle, spalte = OBJEKTE[objekt]
    row = db.eins(f"SELECT {spalte} AS b FROM {tabelle} WHERE id = ?", (oid,))
    return str(row["b"]) if row and row["b"] is not None else ""


def aktion_fuer(methode: str, unterpfad: str | None) -> str:
    if unterpfad:
        return unterpfad.replace("/", "_")  # z. B. plan, massstab, teilen, rueckgaengig, ausrichten
    return {"POST": "angelegt", "PUT": "geaendert", "DELETE": "geloescht"}.get(methode, methode.lower())


def protokoll_einrichten(app: FastAPI, db) -> None:
    @app.middleware("http")
    async def mitschreiben(request: Request, call_next):
        pfad = request.url.path
        if request.method not in ("POST", "PUT", "DELETE") or not pfad.startswith("/api/") or pfad in NICHT_PROTOKOLLIEREN:
            return await call_next(request)
        m = PFAD.match(pfad)
        objekt, oid, unterpfad = (m.group(1), int(m.group(2)) if m.group(2) else None, m.group(3)) if m else (pfad, None, None)
        vorher = _bezeichnung(db, objekt, oid) if request.method == "DELETE" else ""
        antwort = await call_next(request)
        if antwort.status_code >= 400:
            return antwort
        benutzer = auth.benutzer_zur_sitzung(db, request.cookies.get(auth.SITZUNG_COOKIE))
        if benutzer is None:
            return antwort
        # bei Neuanlage die ID aus der Antwort lesen
        if request.method == "POST" and oid is None and antwort.headers.get("content-type", "").startswith("application/json"):
            koerper = b"".join([teil async for teil in antwort.body_iterator])
            try:
                oid = json.loads(koerper).get("id")
            except (ValueError, AttributeError):
                pass
            antwort = Response(koerper, status_code=antwort.status_code, headers=dict(antwort.headers), media_type=antwort.media_type)
        try:
            bezeichnung = vorher or _bezeichnung(db, objekt, oid if isinstance(oid, int) else None)
            db.ausfuehren(
                "INSERT INTO protokoll (benutzer, aktion, objekt, objekt_id, bezeichnung) VALUES (?, ?, ?, ?, ?)",
                (benutzer["benutzername"], aktion_fuer(request.method, unterpfad), objekt, oid if isinstance(oid, int) else None, bezeichnung),
            )
        except Exception:
            log.exception("Protokoll konnte nicht geschrieben werden")
        return antwort


def registrieren(app: FastAPI, db, verwalten) -> None:
    @app.get("/api/protokoll")
    def protokoll(benutzer: str = "", objekt: str = "", seite: int = 0, _: dict = Depends(verwalten)):
        bedingungen, werte = [], []
        if benutzer:
            bedingungen.append("benutzer = ?")
            werte.append(benutzer)
        if objekt:
            bedingungen.append("objekt = ?")
            werte.append(objekt)
        where = f"WHERE {' AND '.join(bedingungen)}" if bedingungen else ""
        eintraege = db.alle(f"SELECT * FROM protokoll {where} ORDER BY id DESC LIMIT 200 OFFSET ?", (*werte, max(0, seite) * 200))
        gesamt = db.eins(f"SELECT COUNT(*) AS n FROM protokoll {where}", tuple(werte))["n"]
        benutzerliste = [r["benutzer"] for r in db.alle("SELECT DISTINCT benutzer FROM protokoll ORDER BY benutzer")]
        return {"eintraege": eintraege, "gesamt": gesamt, "benutzer": benutzerliste}
