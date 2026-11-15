"""Webserver: Oberfläche und JSON-Schnittstelle.

Fehler gibt die Schnittstelle als {"detail": {"code": "...", ...}} zurück; die Oberfläche
übersetzt den Code (fehler.<code> in static/i18n/<sprache>.json).
"""

from __future__ import annotations

import json
import logging
import re
import secrets
import shutil
import sqlite3
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path

from fastapi import Depends, FastAPI, File, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import APP_NAME, __version__, auth, planung
from .config import Pfade, static_ordner
from .db import RECHTE, Datenbank
from .feiertage import BUNDESLAENDER, feiertage
from .plaene import KachelDienst, PdfFehler, leere_kachel, max_zoom_fuer, pdf_seiten, vorschau

log = logging.getLogger(__name__)

MAX_PDF_BYTES = 1024 * 1024 * 1024  # 1 GB
SPRACHEN = {"de": "Deutsch"}  # weitere Sprachen: static/i18n/<code>.json anlegen und hier eintragen


def fehler(status: int, code: str, **extra) -> HTTPException:
    return HTTPException(status_code=status, detail={"code": code, **extra})


# --------------------------------------------------------------------------- Modelle
class Ersteinrichtung(BaseModel):
    benutzername: str = Field(min_length=1, max_length=64)
    anzeigename: str = Field(default="", max_length=100)
    passwort: str


class Anmeldung(BaseModel):
    benutzername: str
    passwort: str


class PasswortAendern(BaseModel):
    altes_passwort: str
    neues_passwort: str


class BenutzerNeu(BaseModel):
    benutzername: str = Field(min_length=1, max_length=64)
    anzeigename: str = Field(default="", max_length=100)
    passwort: str
    rolle: str


class BenutzerAenderung(BaseModel):
    anzeigename: str | None = Field(default=None, max_length=100)
    rolle: str | None = None
    aktiv: bool | None = None
    passwort: str | None = None


class EinstellungenAenderung(BaseModel):
    bundesland: str | None = None
    sprache: str | None = None


class Sondertag(BaseModel):
    datum: date
    name: str = Field(min_length=1, max_length=100)


class Gebaeudeteil(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    kuerzel: str = Field(default="", max_length=10)
    reihenfolge: int = 0


class Stockwerk(BaseModel):
    gebaeudeteil_id: int
    name: str = Field(min_length=1, max_length=100)
    ebene: int = Field(default=0, ge=-20, le=200)


class StockwerkAenderung(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    ebene: int | None = Field(default=None, ge=-20, le=200)
    gebaeudeteil_id: int | None = None


class PlanZuweisung(BaseModel):
    dokument_id: int
    seite: int = Field(ge=1)


class Massstab(BaseModel):
    meter_pro_punkt: float | None = Field(default=None, gt=0)


_BENUTZERNAME = re.compile(r"^[A-Za-z0-9._@-]{1,64}$")


def _benutzername_pruefen(name: str) -> str:
    name = name.strip()
    if not _BENUTZERNAME.match(name):
        raise fehler(400, "benutzername_ungueltig")
    return name


def _passwort_pruefen(pw: str) -> None:
    if len(pw) < auth.MIN_PASSWORT:
        raise fehler(400, "passwort_zu_kurz", min=auth.MIN_PASSWORT)


# --------------------------------------------------------------------------- App
def erstelle_app(pfade: Pfade, kacheln_starten: bool = True) -> FastAPI:
    pfade.anlegen()
    db = Datenbank(pfade.datenbank)
    dienst = KachelDienst(db, pfade)
    bremse = auth.Anmeldebremse()

    @asynccontextmanager
    async def lebenszyklus(app: FastAPI):
        auth.alte_sitzungen_loeschen(db)
        if kacheln_starten:
            dienst.starten()
        yield
        dienst.stoppen()
        db.schliessen()

    app = FastAPI(title=APP_NAME, version=__version__, lifespan=lebenszyklus, docs_url=None, redoc_url=None)
    app.state.db = db
    app.state.kacheln = dienst
    app.state.pfade = pfade

    # ---------------------------------------------------------------- Abhängigkeiten
    def aktueller_benutzer(request: Request) -> dict | None:
        return auth.benutzer_zur_sitzung(db, request.cookies.get(auth.SITZUNG_COOKIE))

    def recht(name: str):
        assert name in RECHTE

        def pruefen(benutzer: dict | None = Depends(aktueller_benutzer)) -> dict:
            if benutzer is None:
                raise fehler(401, "nicht_angemeldet")
            if name not in benutzer["rechte"]:
                raise fehler(403, "keine_berechtigung")
            return benutzer

        return pruefen

    ansehen, bearbeiten, verwalten = recht("ansehen"), recht("bearbeiten"), recht("verwalten")

    def benutzer_anzahl() -> int:
        return db.eins("SELECT COUNT(*) AS n FROM benutzer")["n"]

    def rolle_id(schluessel: str) -> int:
        row = db.eins("SELECT id FROM rollen WHERE schluessel = ?", (schluessel,))
        if row is None:
            raise fehler(400, "rolle_unbekannt")
        return row["id"]

    def anzahl_aktive_admins(ohne_id: int | None = None) -> int:
        return db.eins(
            """SELECT COUNT(*) AS n FROM benutzer b JOIN rollen r ON r.id = b.rolle_id
                WHERE b.aktiv = 1 AND r.rechte LIKE '%"verwalten"%' AND b.id IS NOT ?""",
            (ohne_id,),
        )["n"]

    def cookie_setzen(response: Response, request: Request, token: str) -> None:
        response.set_cookie(
            auth.SITZUNG_COOKIE,
            token,
            max_age=auth.SITZUNG_TAGE * 86400,
            httponly=True,
            samesite="strict",
            secure=request.url.scheme == "https",
        )

    # ---------------------------------------------------------------- Status & Anmeldung
    @app.get("/api/status")
    def status(benutzer: dict | None = Depends(aktueller_benutzer)):
        return {
            "name": APP_NAME,
            "version": __version__,
            "ersteinrichtung": benutzer_anzahl() == 0,
            "benutzer": benutzer,
            "sprache": (benutzer or {}).get("sprache") or db.einstellung("sprache", "de"),
            "sprachen": SPRACHEN,
        }

    @app.post("/api/ersteinrichtung")
    def ersteinrichtung(daten: Ersteinrichtung, request: Request, response: Response):
        name = _benutzername_pruefen(daten.benutzername)
        _passwort_pruefen(daten.passwort)
        with db.transaktion() as con:
            if con.execute("SELECT COUNT(*) FROM benutzer").fetchone()[0] > 0:
                raise fehler(409, "bereits_eingerichtet")
            rid = con.execute("SELECT id FROM rollen WHERE schluessel = 'admin'").fetchone()[0]
            cur = con.execute(
                "INSERT INTO benutzer (benutzername, anzeigename, passwort_hash, rolle_id) VALUES (?, ?, ?, ?)",
                (name, daten.anzeigename.strip() or name, auth.passwort_hash(daten.passwort), rid),
            )
            bid = cur.lastrowid
        cookie_setzen(response, request, auth.sitzung_anlegen(db, bid))
        return {"ok": True}

    @app.post("/api/anmelden")
    def anmelden(daten: Anmeldung, request: Request, response: Response):
        adresse = request.client.host if request.client else "?"
        schluessel = ("u:" + daten.benutzername.lower(), "a:" + adresse)
        if bremse.gesperrt(*schluessel):
            raise fehler(429, "zu_viele_versuche")
        row = db.eins("SELECT id, passwort_hash, aktiv FROM benutzer WHERE benutzername = ?", (daten.benutzername.strip(),))
        if row is None or not row["aktiv"] or not auth.passwort_pruefen(daten.passwort, row["passwort_hash"]):
            bremse.fehlschlag(*schluessel)
            raise fehler(401, "anmeldung_falsch")
        bremse.erfolg(*schluessel)
        cookie_setzen(response, request, auth.sitzung_anlegen(db, row["id"]))
        return {"ok": True}

    @app.post("/api/abmelden")
    def abmelden(request: Request, response: Response):
        token = request.cookies.get(auth.SITZUNG_COOKIE)
        if token:
            auth.sitzung_beenden(db, token)
        response.delete_cookie(auth.SITZUNG_COOKIE)
        return {"ok": True}

    @app.post("/api/ich/passwort")
    def eigenes_passwort(daten: PasswortAendern, request: Request, ich: dict = Depends(ansehen)):
        row = db.eins("SELECT passwort_hash FROM benutzer WHERE id = ?", (ich["id"],))
        if not auth.passwort_pruefen(daten.altes_passwort, row["passwort_hash"]):
            raise fehler(400, "altes_passwort_falsch")
        _passwort_pruefen(daten.neues_passwort)
        token = request.cookies.get(auth.SITZUNG_COOKIE, "")
        with db.transaktion() as con:
            con.execute("UPDATE benutzer SET passwort_hash = ? WHERE id = ?", (auth.passwort_hash(daten.neues_passwort), ich["id"]))
            # andere Sitzungen dieses Benutzers beenden, die aktuelle bleibt
            con.execute(
                "DELETE FROM sitzungen WHERE benutzer_id = ? AND token_hash <> ?",
                (ich["id"], auth._token_hash(token)),
            )
        return {"ok": True}

    # ---------------------------------------------------------------- Benutzer & Rollen
    @app.get("/api/rollen")
    def rollen(_: dict = Depends(verwalten)):
        rows = db.alle("SELECT schluessel, name, rechte, system FROM rollen ORDER BY id")
        for r in rows:
            r["rechte"] = json.loads(r["rechte"])
        return rows

    @app.get("/api/benutzer")
    def benutzer_liste(_: dict = Depends(verwalten)):
        return db.alle(
            """SELECT b.id, b.benutzername, b.anzeigename, b.aktiv, b.erstellt, r.schluessel AS rolle
                 FROM benutzer b JOIN rollen r ON r.id = b.rolle_id ORDER BY b.benutzername"""
        )

    @app.post("/api/benutzer")
    def benutzer_anlegen(daten: BenutzerNeu, _: dict = Depends(verwalten)):
        name = _benutzername_pruefen(daten.benutzername)
        _passwort_pruefen(daten.passwort)
        rid = rolle_id(daten.rolle)
        if db.eins("SELECT 1 FROM benutzer WHERE benutzername = ?", (name,)):
            raise fehler(409, "benutzername_vergeben")
        bid = db.ausfuehren(
            "INSERT INTO benutzer (benutzername, anzeigename, passwort_hash, rolle_id) VALUES (?, ?, ?, ?)",
            (name, daten.anzeigename.strip() or name, auth.passwort_hash(daten.passwort), rid),
        )
        return {"id": bid}

    @app.put("/api/benutzer/{bid}")
    def benutzer_aendern(bid: int, daten: BenutzerAenderung, ich: dict = Depends(verwalten)):
        if db.eins("SELECT 1 FROM benutzer WHERE id = ?", (bid,)) is None:
            raise fehler(404, "nicht_gefunden")
        neue_rolle = rolle_id(daten.rolle) if daten.rolle is not None else None
        wird_admin_los = (daten.aktiv is False) or (
            neue_rolle is not None and "verwalten" not in json.loads(db.eins("SELECT rechte FROM rollen WHERE id = ?", (neue_rolle,))["rechte"])
        )
        if wird_admin_los and anzahl_aktive_admins(ohne_id=bid) == 0:
            raise fehler(400, "letzter_admin")
        if daten.passwort is not None:
            _passwort_pruefen(daten.passwort)
        with db.transaktion() as con:
            if daten.anzeigename is not None:
                con.execute("UPDATE benutzer SET anzeigename = ? WHERE id = ?", (daten.anzeigename.strip(), bid))
            if neue_rolle is not None:
                con.execute("UPDATE benutzer SET rolle_id = ? WHERE id = ?", (neue_rolle, bid))
            if daten.aktiv is not None:
                con.execute("UPDATE benutzer SET aktiv = ? WHERE id = ?", (int(daten.aktiv), bid))
                if not daten.aktiv:
                    con.execute("DELETE FROM sitzungen WHERE benutzer_id = ?", (bid,))
            if daten.passwort is not None:
                con.execute("UPDATE benutzer SET passwort_hash = ? WHERE id = ?", (auth.passwort_hash(daten.passwort), bid))
                if bid != ich["id"]:
                    con.execute("DELETE FROM sitzungen WHERE benutzer_id = ?", (bid,))
        return {"ok": True}

    @app.delete("/api/benutzer/{bid}")
    def benutzer_loeschen(bid: int, ich: dict = Depends(verwalten)):
        if bid == ich["id"]:
            raise fehler(400, "sich_selbst_loeschen")
        if anzahl_aktive_admins(ohne_id=bid) == 0:
            raise fehler(400, "letzter_admin")
        db.ausfuehren("DELETE FROM benutzer WHERE id = ?", (bid,))
        return {"ok": True}

    # ---------------------------------------------------------------- Einstellungen & Feiertage
    @app.get("/api/einstellungen")
    def einstellungen(_: dict = Depends(ansehen)):
        return {
            "bundesland": db.einstellung("bundesland", "NW"),
            "sprache": db.einstellung("sprache", "de"),
            "bundeslaender": BUNDESLAENDER,
            "sprachen": SPRACHEN,
        }

    @app.put("/api/einstellungen")
    def einstellungen_aendern(daten: EinstellungenAenderung, _: dict = Depends(verwalten)):
        if daten.bundesland is not None:
            if daten.bundesland not in BUNDESLAENDER:
                raise fehler(400, "bundesland_unbekannt")
            db.setze_einstellung("bundesland", daten.bundesland)
        if daten.sprache is not None:
            if daten.sprache not in SPRACHEN:
                raise fehler(400, "sprache_unbekannt")
            db.setze_einstellung("sprache", daten.sprache)
        return {"ok": True}

    @app.get("/api/feiertage")
    def feiertage_liste(jahr: int | None = None, _: dict = Depends(ansehen)):
        jahr = jahr or date.today().year
        if not 1900 <= jahr <= 2200:
            raise fehler(400, "jahr_ungueltig")
        bl = db.einstellung("bundesland", "NW")
        tage = [{"datum": d.isoformat(), "schluessel": k, "art": "gesetzlich"} for d, k in feiertage(jahr, bl)]
        for s in db.alle("SELECT id, datum, name FROM sondertage WHERE datum LIKE ? ORDER BY datum", (f"{jahr}-%",)):
            tage.append({"datum": s["datum"], "name": s["name"], "art": "sondertag", "id": s["id"]})
        tage.sort(key=lambda t: t["datum"])
        return {"jahr": jahr, "bundesland": bl, "tage": tage}

    @app.post("/api/sondertage")
    def sondertag_anlegen(daten: Sondertag, _: dict = Depends(verwalten)):
        return {"id": db.ausfuehren("INSERT INTO sondertage (datum, name) VALUES (?, ?)", (daten.datum.isoformat(), daten.name.strip()))}

    @app.delete("/api/sondertage/{sid}")
    def sondertag_loeschen(sid: int, _: dict = Depends(verwalten)):
        db.ausfuehren("DELETE FROM sondertage WHERE id = ?", (sid,))
        return {"ok": True}

    # ---------------------------------------------------------------- Gebäude & Stockwerke
    def plan_info(plan_id: int | None) -> dict | None:
        if plan_id is None:
            return None
        p = db.eins(
            """SELECT p.id, p.dokument_id, d.dateiname, p.seite, p.breite, p.hoehe, p.max_zoom,
                      p.status, p.fortschritt, p.fehler
                 FROM plaene p JOIN dokumente d ON d.id = p.dokument_id WHERE p.id = ?""",
            (plan_id,),
        )
        return p

    @app.get("/api/gebaeude")
    def gebaeude(_: dict = Depends(ansehen)):
        teile = db.alle("SELECT * FROM gebaeudeteile ORDER BY reihenfolge, name")
        stockwerke = db.alle("SELECT * FROM stockwerke ORDER BY ebene DESC, name")
        for t in teile:
            t["stockwerke"] = []
            for s in stockwerke:
                if s["gebaeudeteil_id"] == t["id"]:
                    s = dict(s)
                    s["plan"] = plan_info(s["plan_id"])
                    t["stockwerke"].append(s)
        return teile

    @app.post("/api/gebaeudeteile")
    def gebaeudeteil_anlegen(daten: Gebaeudeteil, _: dict = Depends(bearbeiten)):
        return {
            "id": db.ausfuehren(
                "INSERT INTO gebaeudeteile (name, kuerzel, reihenfolge) VALUES (?, ?, ?)",
                (daten.name.strip(), daten.kuerzel.strip(), daten.reihenfolge),
            )
        }

    @app.put("/api/gebaeudeteile/{gid}")
    def gebaeudeteil_aendern(gid: int, daten: Gebaeudeteil, _: dict = Depends(bearbeiten)):
        db.ausfuehren(
            "UPDATE gebaeudeteile SET name = ?, kuerzel = ?, reihenfolge = ? WHERE id = ?",
            (daten.name.strip(), daten.kuerzel.strip(), daten.reihenfolge, gid),
        )
        return {"ok": True}

    @app.delete("/api/gebaeudeteile/{gid}")
    def gebaeudeteil_loeschen(gid: int, _: dict = Depends(bearbeiten)):
        plaene = [r["plan_id"] for r in db.alle("SELECT plan_id FROM stockwerke WHERE gebaeudeteil_id = ? AND plan_id IS NOT NULL", (gid,))]
        db.ausfuehren("DELETE FROM gebaeudeteile WHERE id = ?", (gid,))
        for pid in plaene:
            plan_entfernen(pid)
        return {"ok": True}

    @app.post("/api/stockwerke")
    def stockwerk_anlegen(daten: Stockwerk, _: dict = Depends(bearbeiten)):
        if db.eins("SELECT 1 FROM gebaeudeteile WHERE id = ?", (daten.gebaeudeteil_id,)) is None:
            raise fehler(404, "nicht_gefunden")
        return {
            "id": db.ausfuehren(
                "INSERT INTO stockwerke (gebaeudeteil_id, name, ebene) VALUES (?, ?, ?)",
                (daten.gebaeudeteil_id, daten.name.strip(), daten.ebene),
            )
        }

    def stockwerk_holen(sid: int) -> dict:
        s = db.eins("SELECT * FROM stockwerke WHERE id = ?", (sid,))
        if s is None:
            raise fehler(404, "nicht_gefunden")
        return s

    @app.get("/api/stockwerke/{sid}")
    def stockwerk(sid: int, _: dict = Depends(ansehen)):
        s = stockwerk_holen(sid)
        s["plan"] = plan_info(s["plan_id"])
        s["gebaeudeteil"] = db.eins("SELECT id, name, kuerzel FROM gebaeudeteile WHERE id = ?", (s["gebaeudeteil_id"],))
        return s

    @app.put("/api/stockwerke/{sid}")
    def stockwerk_aendern(sid: int, daten: StockwerkAenderung, _: dict = Depends(bearbeiten)):
        stockwerk_holen(sid)
        if daten.gebaeudeteil_id is not None and db.eins("SELECT 1 FROM gebaeudeteile WHERE id = ?", (daten.gebaeudeteil_id,)) is None:
            raise fehler(404, "nicht_gefunden")
        with db.transaktion() as con:
            if daten.name is not None:
                con.execute("UPDATE stockwerke SET name = ? WHERE id = ?", (daten.name.strip(), sid))
            if daten.ebene is not None:
                con.execute("UPDATE stockwerke SET ebene = ? WHERE id = ?", (daten.ebene, sid))
            if daten.gebaeudeteil_id is not None:
                con.execute("UPDATE stockwerke SET gebaeudeteil_id = ? WHERE id = ?", (daten.gebaeudeteil_id, sid))
        return {"ok": True}

    @app.delete("/api/stockwerke/{sid}")
    def stockwerk_loeschen(sid: int, _: dict = Depends(bearbeiten)):
        s = stockwerk_holen(sid)
        db.ausfuehren("DELETE FROM stockwerke WHERE id = ?", (sid,))
        if s["plan_id"]:
            plan_entfernen(s["plan_id"])
        return {"ok": True}

    def plan_entfernen(plan_id: int) -> None:
        if db.eins("SELECT 1 FROM stockwerke WHERE plan_id = ?", (plan_id,)):
            return  # noch woanders in Gebrauch
        dienst.abbrechen(plan_id)
        db.ausfuehren("DELETE FROM plaene WHERE id = ?", (plan_id,))
        shutil.rmtree(dienst.ordner(plan_id), ignore_errors=True)

    @app.put("/api/stockwerke/{sid}/plan")
    def plan_zuweisen(sid: int, daten: PlanZuweisung, _: dict = Depends(bearbeiten)):
        s = stockwerk_holen(sid)
        dok = db.eins("SELECT * FROM dokumente WHERE id = ?", (daten.dokument_id,))
        if dok is None:
            raise fehler(404, "nicht_gefunden")
        seiten = json.loads(dok["seiten"])
        if daten.seite > len(seiten):
            raise fehler(400, "seite_ungueltig")
        seite = seiten[daten.seite - 1]
        alt = s["plan_id"]
        # gleiche Seite schon als Plan vorhanden? Dann wiederverwenden statt neu zu rechnen.
        vorhanden = db.eins(
            "SELECT id FROM plaene WHERE dokument_id = ? AND seite = ? AND status <> 'fehler'",
            (daten.dokument_id, daten.seite),
        )
        if vorhanden:
            pid = vorhanden["id"]
        else:
            pid = db.ausfuehren(
                "INSERT INTO plaene (dokument_id, seite, breite, hoehe, max_zoom) VALUES (?, ?, ?, ?, ?)",
                (daten.dokument_id, daten.seite, seite["breite"], seite["hoehe"], max_zoom_fuer(seite["breite"], seite["hoehe"])),
            )
        # Maßstab gehört zur Planseite: bei neuem Plan zurücksetzen
        db.ausfuehren("UPDATE stockwerke SET plan_id = ?, meter_pro_punkt = NULL WHERE id = ?", (pid, sid))
        if not vorhanden:
            dienst.einreihen(pid)
        if alt and alt != pid:
            plan_entfernen(alt)
        return {"plan_id": pid}

    @app.delete("/api/stockwerke/{sid}/plan")
    def plan_entfernen_von_stockwerk(sid: int, _: dict = Depends(bearbeiten)):
        s = stockwerk_holen(sid)
        db.ausfuehren("UPDATE stockwerke SET plan_id = NULL, meter_pro_punkt = NULL WHERE id = ?", (sid,))
        if s["plan_id"]:
            plan_entfernen(s["plan_id"])
        return {"ok": True}

    @app.post("/api/plaene/{pid}/neu")
    def plan_neu_erzeugen(pid: int, _: dict = Depends(bearbeiten)):
        if db.eins("SELECT 1 FROM plaene WHERE id = ?", (pid,)) is None:
            raise fehler(404, "nicht_gefunden")
        db.ausfuehren("UPDATE plaene SET status = 'wartet' WHERE id = ?", (pid,))
        dienst.einreihen(pid)
        return {"ok": True}

    @app.put("/api/stockwerke/{sid}/massstab")
    def massstab_setzen(sid: int, daten: Massstab, _: dict = Depends(bearbeiten)):
        stockwerk_holen(sid)
        db.ausfuehren("UPDATE stockwerke SET meter_pro_punkt = ? WHERE id = ?", (daten.meter_pro_punkt, sid))
        return {"ok": True}

    # ---------------------------------------------------------------- Dokumente (PDF)
    @app.get("/api/dokumente")
    def dokumente(_: dict = Depends(ansehen)):
        rows = db.alle("SELECT id, dateiname, groesse, seiten, hochgeladen FROM dokumente ORDER BY hochgeladen DESC, id DESC")
        for r in rows:
            r["seiten"] = json.loads(r["seiten"])
            r["verwendet"] = db.eins("SELECT COUNT(*) AS n FROM plaene WHERE dokument_id = ?", (r["id"],))["n"]
        return rows

    @app.post("/api/dokumente")
    async def dokument_hochladen(datei: UploadFile = File(...), ich: dict = Depends(bearbeiten)):
        tmp = pfade.dokumente / f"upload-{secrets.token_hex(8)}.tmp"
        groesse = 0
        try:
            with tmp.open("wb") as f:
                while chunk := await datei.read(1024 * 1024):
                    groesse += len(chunk)
                    if groesse > MAX_PDF_BYTES:
                        raise fehler(413, "datei_zu_gross")
                    f.write(chunk)
            with tmp.open("rb") as f:
                if f.read(5) != b"%PDF-":
                    raise fehler(400, "kein_pdf")
            try:
                seiten = pdf_seiten(tmp)
            except PdfFehler as e:
                raise fehler(400, "pdf_defekt", grund=str(e))
            name = Path(datei.filename or "plan.pdf").name[:200]
            did = db.ausfuehren(
                "INSERT INTO dokumente (dateiname, groesse, seiten, hochgeladen_von) VALUES (?, ?, ?, ?)",
                (name, groesse, json.dumps(seiten), ich["id"]),
            )
            tmp.replace(pfade.dokumente / f"{did}.pdf")
        finally:
            tmp.unlink(missing_ok=True)
        return {"id": did, "dateiname": name, "seiten": seiten}

    @app.delete("/api/dokumente/{did}")
    def dokument_loeschen(did: int, _: dict = Depends(bearbeiten)):
        if db.eins("SELECT 1 FROM plaene WHERE dokument_id = ?", (did,)):
            raise fehler(409, "dokument_in_verwendung")
        db.ausfuehren("DELETE FROM dokumente WHERE id = ?", (did,))
        (pfade.dokumente / f"{did}.pdf").unlink(missing_ok=True)
        for v in pfade.dokumente.glob(f"{did}_s*.png"):
            v.unlink(missing_ok=True)
        return {"ok": True}

    @app.get("/api/dokumente/{did}/vorschau/{seite}")
    def dokument_vorschau(did: int, seite: int, _: dict = Depends(ansehen)):
        dok = db.eins("SELECT seiten FROM dokumente WHERE id = ?", (did,))
        if dok is None or not 1 <= seite <= len(json.loads(dok["seiten"])):
            raise fehler(404, "nicht_gefunden")
        bild = vorschau(pfade.dokumente / f"{did}.pdf", seite, pfade.dokumente / f"{did}_s{seite}.png")
        return FileResponse(bild, media_type="image/png", headers={"Cache-Control": "private, max-age=86400"})

    # ---------------------------------------------------------------- Kacheln
    @app.get("/api/plaene/{pid}/kacheln/{z}/{x}/{y}.png")
    def kachel(pid: int, z: int, x: int, y: int, _: dict = Depends(ansehen)):
        pfad = dienst.ordner(pid) / str(z) / f"{x}_{y}.png"
        kopf = {"Cache-Control": "private, max-age=604800"}
        if pfad.is_file():
            return FileResponse(pfad, media_type="image/png", headers=kopf)
        return Response(leere_kachel(), media_type="image/png", headers=kopf)

    # ---------------------------------------------------------------- Netz, Stammdaten, Lieferungen, Simulation
    planung.registrieren(app, db, fehler, ansehen, bearbeiten)

    @app.exception_handler(sqlite3.IntegrityError)
    async def in_verwendung(request: Request, exc):
        log.info("Integritätsfehler bei %s: %s", request.url.path, exc)
        return JSONResponse({"detail": {"code": "in_verwendung"}}, status_code=409)

    # ---------------------------------------------------------------- Oberfläche
    statisch = static_ordner()

    @app.exception_handler(404)
    async def nicht_gefunden(request: Request, exc):
        if request.url.path.startswith("/api/"):
            detail = getattr(exc, "detail", None)
            if not isinstance(detail, dict):
                detail = {"code": "nicht_gefunden"}
            return JSONResponse({"detail": detail}, status_code=404)
        return FileResponse(statisch / "index.html")

    app.mount("/", StaticFiles(directory=statisch, html=True), name="static")
    return app
