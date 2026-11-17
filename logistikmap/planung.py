"""Schnittstellen für Flächen, Wegenetz, Stammdaten, Lieferungen und Ablauf-Simulation."""

from __future__ import annotations

import contextvars
import copy
import json
import logging
import secrets
import threading
import time
from urllib.parse import quote
import random
import math
import re
from datetime import date
from typing import Literal

from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field

from . import export, standort

from .db import Datenbank
from .feiertage import feiertage
from .netz import KNOTEN_ARTEN, Netz, WegFehler
from .regeln import RegelFehler, gilt_am, normalisieren
from .simulation import Simulation

log = logging.getLogger(__name__)

UHRZEIT = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
FARBE = re.compile(r"^(#[0-9a-fA-F]{6})?$")
RUECKWEG_MODI = ("leer", "beladen", "spaeter", "keiner")
RICHTUNGEN = ("versorgung", "entsorgung", "intern")
VORTAG_AB = "16:00"  # Lieferungen ab dieser Uhrzeit können in den nächsten Tag hineinlaufen


# --------------------------------------------------------------------------- Modelle
class Transportart(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    farbe: str = "#1f5f8b"
    geschwindigkeit: float = Field(gt=0, le=20)
    ladezeit: float = Field(ge=0, le=7200)
    entladezeit: float = Field(ge=0, le=7200)
    wagen_pro_fahrt: int = Field(ge=1, le=50)
    anzahl: int = Field(ge=0, le=10000)
    aufzug_exklusiv: bool = False
    treppe: bool = False
    schichten: list["Schicht"] = []


class Schicht(BaseModel):
    von: str
    bis: str
    anzahl: int = Field(ge=0, le=10000)
    wochentage: list[int] = []


class Wagentyp(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    plaetze: float = Field(gt=0, le=100)


class Grundlast(BaseModel):
    """Aufzug ist in diesem Zeitfenster zu prozent % durch Personen belegt."""

    von: str
    bis: str
    prozent: float = Field(ge=0, le=100)
    wochentage: list[int] = [1, 2, 3, 4, 5]


class AufzugModell(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    art: str = "aufzug"
    plaetze: float = Field(ge=0, le=100)
    fahrzeit_etage: float = Field(ge=0, le=600)
    tuerzeit: float = Field(ge=0, le=600)
    raeumzeit: float = Field(ge=0, le=600)
    anfahrt: float = Field(ge=0, le=1800)
    transportarten: list[int] = []
    grundlast: list[Grundlast] = []  # Personenfahrten: Anteil der Zeit belegt je Zeitfenster


class Flaeche(BaseModel):
    stockwerk_id: int
    art: str = "raum"
    name: str = Field(min_length=1, max_length=100)
    nummer: str = Field(default="", max_length=30)
    farbe: str = ""
    punkte: list[tuple[float, float]]
    parent_id: int | None = None


class FlaecheAenderung(BaseModel):
    art: str | None = None
    name: str | None = Field(default=None, min_length=1, max_length=100)
    nummer: str | None = Field(default=None, max_length=30)
    farbe: str | None = None
    punkte: list[tuple[float, float]] | None = None
    parent_id: int | None = None


class Knoten(BaseModel):
    stockwerk_id: int
    x: float
    y: float
    art: str = "weg"
    name: str = Field(default="", max_length=100)
    aufzug_id: int | None = None
    kapazitaet: int | None = Field(default=None, ge=1, le=1000)
    minuten_je_einheit: float | None = Field(default=None, ge=0, le=240)  # nur Tore: Entladen je Palette/Wagen
    minuten_je_einheit_bis: float | None = Field(default=None, ge=0, le=240)  # Streuung: von–bis


class Vereinen(BaseModel):
    mit: int


class KnotenAenderung(BaseModel):
    ohne_hinweis: bool | None = None  # „Nein“ bei „Lücken prüfen“
    x: float | None = None
    y: float | None = None
    art: str | None = None
    name: str | None = Field(default=None, max_length=100)
    aufzug_id: int | None = None
    kapazitaet: int | None = Field(default=None, ge=0, le=1000)
    minuten_je_einheit: float | None = Field(default=None, ge=0, le=240)
    minuten_je_einheit_bis: float | None = Field(default=None, ge=0, le=240)


class Kante(BaseModel):
    von: int
    nach: int
    laenge_m: float | None = Field(default=None, gt=0, le=100000)
    kapazitaet: int | None = Field(default=None, ge=1, le=1000)
    gesperrt: list[int] = []
    name: str = Field(default="", max_length=100)


class KanteAenderung(BaseModel):
    laenge_m: float | None = Field(default=None, ge=0, le=100000)
    kapazitaet: int | None = Field(default=None, ge=0, le=1000)
    gesperrt: list[int] | None = None
    name: str | None = Field(default=None, max_length=100)


class Szenario(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    beschreibung: str = Field(default="", max_length=2000)
    aenderungen: dict = {}


class RechnungAuftrag(BaseModel):
    art: Literal["streuung", "bedarf"]
    parameter: dict = {}


class Passpaar(BaseModel):
    alt_x: float
    alt_y: float
    neu_x: float
    neu_y: float


class Ausrichten(BaseModel):
    paare: list[Passpaar]


class Teilen(BaseModel):
    x: float
    y: float


class Ladung(BaseModel):
    wagentyp_id: int
    anzahl: int = Field(ge=0, le=1000)


class Rueckweg(BaseModel):
    modus: str = "leer"
    uhrzeit: str | None = None
    ziel_id: int | None = None


Transportart.model_rebuild()


class Lieferung(BaseModel):
    name: str = Field(default="", max_length=150)  # leer: „Start → Ziel“
    lieferant: str = Field(default="", max_length=150)
    richtung: str = "versorgung"
    transportart_id: int | None = None  # leer: die erste Transportart, die den Weg schafft
    start_id: int
    ziel_id: int
    uhrzeit: str
    spaetestens: str | None = None
    streuung: int = Field(default=0, ge=0, le=240)  # Ankunft schwankt um ± Minuten
    ladung: list[Ladung] = []
    via: list[int] = []
    regel: dict = {}
    rueckweg: Rueckweg = Rueckweg()
    aktiv: bool = True
    notiz: str = Field(default="", max_length=2000)


# --------------------------------------------------------------------------- Geometrie
def im_polygon(x: float, y: float, punkte: list) -> bool:
    innen = False
    j = len(punkte) - 1
    for i in range(len(punkte)):
        xi, yi = punkte[i]
        xj, yj = punkte[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            innen = not innen
        j = i
    return innen


def flaeche_inhalt(punkte: list) -> float:
    return abs(sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(punkte, punkte[1:] + punkte[:1]))) / 2


def transformation(paare: list[tuple[float, float, float, float]]):
    """Abbildung alt → neu aus Passpunkten.

    2 Paare: Ähnlichkeit (Verschieben, Drehen, gleichmäßig Skalieren).
    ab 3 Paaren: affin nach kleinsten Quadraten.
    Gibt (a, b, c, d, e, f) zurück mit x' = a·x + b·y + c, y' = d·x + e·y + f.
    """
    if len(paare) < 2:
        raise ValueError("zu_wenige_passpunkte")
    if len(paare) == 2:
        (x1, y1, u1, v1), (x2, y2, u2, v2) = paare
        dx, dy, du, dv = x2 - x1, y2 - y1, u2 - u1, v2 - v1
        n = dx * dx + dy * dy
        if n == 0:
            raise ValueError("passpunkte_gleich")
        a = (dx * du + dy * dv) / n
        b = (dx * dv - dy * du) / n
        # x' = a·x − b·y + c ; y' = b·x + a·y + f
        c = u1 - a * x1 + b * y1
        f = v1 - b * x1 - a * y1
        return (a, -b, c, b, a, f)
    # Normalgleichungen für [x y 1]·[a b c]ᵀ = u bzw. v
    sxx = sum(x * x for x, y, *_ in paare)
    sxy = sum(x * y for x, y, *_ in paare)
    syy = sum(y * y for x, y, *_ in paare)
    sx = sum(x for x, *_ in paare)
    sy = sum(y for _, y, *_ in paare)
    n = len(paare)
    m = [[sxx, sxy, sx], [sxy, syy, sy], [sx, sy, n]]

    def loesen(rechts):
        a = [row[:] + [r_] for row, r_ in zip(m, rechts)]
        for i in range(3):
            piv = max(range(i, 3), key=lambda k: abs(a[k][i]))
            if abs(a[piv][i]) < 1e-12:
                raise ValueError("passpunkte_auf_einer_linie")
            a[i], a[piv] = a[piv], a[i]
            for k in range(3):
                if k != i:
                    fak = a[k][i] / a[i][i]
                    a[k] = [ak - fak * ai for ak, ai in zip(a[k], a[i])]
        return [a[i][3] / a[i][i] for i in range(3)]

    abc = loesen([sum(x * u for x, y, u, v in paare), sum(y * u for x, y, u, v in paare), sum(u for x, y, u, v in paare)])
    def_ = loesen([sum(x * v for x, y, u, v in paare), sum(y * v for x, y, u, v in paare), sum(v for x, y, u, v in paare)])
    return (*abc, *def_)


def szenario_anwenden(aenderungen: dict, lieferungen: list[dict], stamm: dict, netz: Netz) -> list[dict]:
    """Wendet die Abweichungen eines Szenarios auf die geladenen Daten an (nur im Speicher)."""
    aend = aenderungen or {}
    for l in lieferungen:
        for k, v in (aend.get("lieferungen", {}).get(str(l["id"])) or {}).items():
            if k in ("uhrzeit", "spaetestens", "aktiv", "transportart_id", "ladung", "start_id", "ziel_id", "rueckweg", "via"):
                l[k] = v
    for t in stamm["transportarten"]:
        for k, v in (aend.get("transportarten", {}).get(str(t["id"])) or {}).items():
            if k in ("anzahl", "geschwindigkeit", "ladezeit", "entladezeit", "wagen_pro_fahrt", "schichten", "aufzug_exklusiv"):
                t[k] = v
    for aid, werte in (aend.get("aufzuege") or {}).items():
        a = netz.aufzuege.get(int(aid))
        if a is None:
            continue
        if werte.get("ausser_betrieb"):
            netz.aufzuege.pop(int(aid))
            netz.aufzug_halte.pop(int(aid), None)
            continue
        for k, v in werte.items():
            if k in ("plaetze", "fahrzeit_etage", "tuerzeit", "raeumzeit", "anfahrt"):
                a[k] = v
    alle_ta = [t["id"] for t in stamm["transportarten"]]
    for kid, werte in (aend.get("kanten") or {}).items():
        k = netz.kanten.get(int(kid))
        if k is not None and werte.get("gesperrt"):
            k["gesperrt"] = alle_ta
        if k is not None and "kapazitaet" in werte:
            k["kapazitaet"] = werte["kapazitaet"] or None
    for nid, werte in (aend.get("knoten") or {}).items():
        n = netz.knoten.get(int(nid))
        if n is not None and "kapazitaet" in werte:
            n["kapazitaet"] = werte["kapazitaet"] or None
    return lieferungen


def registrieren(app: FastAPI, db: Datenbank, fehler, ansehen, bearbeiten, lieferungen_recht=None, verwalten=None, pfade=None) -> None:
    def ort() -> int:
        return standort.aktuell(db)

    lieferungen_recht = lieferungen_recht or bearbeiten
    def holen(tabelle: str, rid: int) -> dict:
        row = db.eins(f"SELECT * FROM {tabelle} WHERE id = ?", (rid,))
        if row is None or not standort.darf(db, tabelle, rid):  # anderes Krankenhaus, das der Benutzer nicht sehen darf
            raise fehler(404, "nicht_gefunden")
        return row

    def farbe_pruefen(f: str) -> None:
        if not FARBE.match(f or ""):
            raise fehler(400, "farbe_ungueltig")

    # ---------------------------------------------------------------- Stammdaten
    def stammdaten() -> dict:
        auf = db.alle("SELECT * FROM aufzuege WHERE standort_id = ? ORDER BY art, name", (ort(),))
        for a in auf:
            a["transportarten"] = json.loads(a["transportarten"])
            a["grundlast"] = json.loads(a.get("grundlast") or "[]")
        ta = db.alle("SELECT * FROM transportarten WHERE standort_id = ? ORDER BY id", (ort(),))
        for t in ta:
            t["aufzug_exklusiv"], t["treppe"] = bool(t["aufzug_exklusiv"]), bool(t["treppe"])
            t["schichten"] = json.loads(t.get("schichten") or "[]")
        return {"transportarten": ta, "wagentypen": db.alle("SELECT * FROM wagentypen WHERE standort_id = ? ORDER BY name", (ort(),)), "aufzuege": auf}

    @app.get("/api/stammdaten")
    def stammdaten_lesen(_: dict = Depends(ansehen)):
        return stammdaten()

    def schichten_pruefen(schichten: list) -> str:
        for sch in schichten:
            if not UHRZEIT.match(sch.von) or not UHRZEIT.match(sch.bis):
                raise fehler(400, "uhrzeit_ungueltig")
            if any(not 1 <= t <= 7 for t in sch.wochentage):
                raise fehler(400, "regel_ungueltig", feld="wochentage")
        return json.dumps([sch.model_dump() for sch in schichten])

    @app.post("/api/transportarten")
    def transportart_anlegen(d: Transportart, _: dict = Depends(bearbeiten)):
        farbe_pruefen(d.farbe)
        return {"id": db.ausfuehren(
            "INSERT INTO transportarten (name, farbe, geschwindigkeit, ladezeit, entladezeit, wagen_pro_fahrt, anzahl, aufzug_exklusiv, treppe, schichten, standort_id) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (d.name.strip(), d.farbe, d.geschwindigkeit, d.ladezeit, d.entladezeit, d.wagen_pro_fahrt, d.anzahl, int(d.aufzug_exklusiv), int(d.treppe), schichten_pruefen(d.schichten), ort()))}

    @app.put("/api/transportarten/{tid}")
    def transportart_aendern(tid: int, d: Transportart, _: dict = Depends(bearbeiten)):
        holen("transportarten", tid)
        farbe_pruefen(d.farbe)
        db.ausfuehren(
            "UPDATE transportarten SET name=?, farbe=?, geschwindigkeit=?, ladezeit=?, entladezeit=?, wagen_pro_fahrt=?, anzahl=?, aufzug_exklusiv=?, treppe=?, schichten=? WHERE id=?",
            (d.name.strip(), d.farbe, d.geschwindigkeit, d.ladezeit, d.entladezeit, d.wagen_pro_fahrt, d.anzahl, int(d.aufzug_exklusiv), int(d.treppe), schichten_pruefen(d.schichten), tid))
        return {"ok": True}

    @app.delete("/api/transportarten/{tid}")
    def transportart_loeschen(tid: int, _: dict = Depends(bearbeiten)):
        if db.eins("SELECT 1 FROM lieferungen WHERE transportart_id = ?", (tid,)):
            raise fehler(409, "transportart_in_verwendung")
        db.ausfuehren("DELETE FROM transportarten WHERE id = ?", (tid,))
        return {"ok": True}

    @app.post("/api/wagentypen")
    def wagentyp_anlegen(d: Wagentyp, _: dict = Depends(bearbeiten)):
        return {"id": db.ausfuehren("INSERT INTO wagentypen (name, plaetze, standort_id) VALUES (?, ?, ?)", (d.name.strip(), d.plaetze, ort()))}

    @app.put("/api/wagentypen/{wid}")
    def wagentyp_aendern(wid: int, d: Wagentyp, _: dict = Depends(bearbeiten)):
        holen("wagentypen", wid)
        db.ausfuehren("UPDATE wagentypen SET name = ?, plaetze = ? WHERE id = ?", (d.name.strip(), d.plaetze, wid))
        return {"ok": True}

    @app.delete("/api/wagentypen/{wid}")
    def wagentyp_loeschen(wid: int, _: dict = Depends(bearbeiten)):
        for l in db.alle("SELECT ladung FROM lieferungen"):
            if any(p.get("wagentyp_id") == wid for p in json.loads(l["ladung"])):
                raise fehler(409, "wagentyp_in_verwendung")
        db.ausfuehren("DELETE FROM wagentypen WHERE id = ?", (wid,))
        return {"ok": True}

    def aufzug_pruefen(d: AufzugModell) -> str:
        if d.art not in ("aufzug", "treppe"):
            raise fehler(400, "art_ungueltig")
        for g in d.grundlast:
            if not UHRZEIT.match(g.von) or not UHRZEIT.match(g.bis):
                raise fehler(400, "uhrzeit_ungueltig")
            if any(not 1 <= t <= 7 for t in g.wochentage):
                raise fehler(400, "regel_ungueltig", feld="wochentage")
        return json.dumps([g.model_dump() for g in d.grundlast])

    @app.post("/api/aufzuege")
    def aufzug_anlegen(d: AufzugModell, _: dict = Depends(bearbeiten)):
        grundlast = aufzug_pruefen(d)
        return {"id": db.ausfuehren(
            "INSERT INTO aufzuege (name, art, plaetze, fahrzeit_etage, tuerzeit, raeumzeit, anfahrt, transportarten, standort_id, grundlast) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (d.name.strip(), d.art, d.plaetze, d.fahrzeit_etage, d.tuerzeit, d.raeumzeit, d.anfahrt, json.dumps(d.transportarten), ort(), grundlast))}

    @app.put("/api/aufzuege/{aid}")
    def aufzug_aendern(aid: int, d: AufzugModell, _: dict = Depends(bearbeiten)):
        holen("aufzuege", aid)
        grundlast = aufzug_pruefen(d)
        db.ausfuehren(
            "UPDATE aufzuege SET name=?, art=?, plaetze=?, fahrzeit_etage=?, tuerzeit=?, raeumzeit=?, anfahrt=?, transportarten=?, grundlast=? WHERE id=?",
            (d.name.strip(), d.art, d.plaetze, d.fahrzeit_etage, d.tuerzeit, d.raeumzeit, d.anfahrt, json.dumps(d.transportarten), grundlast, aid))
        return {"ok": True}

    @app.delete("/api/aufzuege/{aid}")
    def aufzug_loeschen(aid: int, _: dict = Depends(bearbeiten)):
        db.ausfuehren("DELETE FROM aufzuege WHERE id = ?", (aid,))
        return {"ok": True}

    # ---------------------------------------------------------------- Rückgängig
    VERLAUF_MAX = 50

    def merken(stockwerk_id: int, request: Request | None, text: str) -> None:
        """Schnappschuss des Stockwerks vor einer Änderung.

        Schickt die Oberfläche den Kopf X-Rueckgaengig-Gruppe, bilden alle Änderungen mit derselben
        Gruppe einen einzigen Rückgängig-Schritt (z. B. Flur teilen + Punkt + Wegstück bei einem Klick).
        """
        benutzer = ""
        gruppe = None
        if request is not None:
            from . import auth

            b = auth.benutzer_zur_sitzung(db, request.cookies.get(auth.SITZUNG_COOKIE))
            benutzer = b["benutzername"] if b else ""
            gruppe = (request.headers.get("X-Rueckgaengig-Gruppe") or "")[:64] or None
        if gruppe:
            letzter = db.eins("SELECT gruppe, benutzer FROM netz_verlauf WHERE stockwerk_id = ? ORDER BY id DESC LIMIT 1", (stockwerk_id,))
            if letzter and letzter["gruppe"] == gruppe and letzter["benutzer"] == benutzer:
                return  # gehört zum selben Schritt, der Zustand davor ist schon gemerkt
        knoten = db.alle("SELECT * FROM knoten WHERE stockwerk_id = ?", (stockwerk_id,))
        ids = [k["id"] for k in knoten]
        kanten = []
        if ids:
            platz = ",".join("?" * len(ids))
            kanten = db.alle(f"SELECT * FROM kanten WHERE von IN ({platz}) OR nach IN ({platz})", (*ids, *ids))
        flaechen = db.alle("SELECT * FROM flaechen WHERE stockwerk_id = ?", (stockwerk_id,))
        inhalt = {"knoten": knoten, "kanten": kanten, "flaechen": flaechen}
        if text == "ausrichten":  # nur Ausrichten ändert den Maßstab mit
            sw = db.eins("SELECT meter_pro_punkt FROM stockwerke WHERE id = ?", (stockwerk_id,))
            inhalt["meter_pro_punkt"] = sw["meter_pro_punkt"] if sw else None
        db.ausfuehren(
            "INSERT INTO netz_verlauf (stockwerk_id, benutzer, beschreibung, daten, gruppe) VALUES (?, ?, ?, ?, ?)",
            (stockwerk_id, benutzer, text, json.dumps(inhalt), gruppe),
        )
        db.ausfuehren(
            "DELETE FROM netz_verlauf WHERE stockwerk_id = ? AND id NOT IN (SELECT id FROM netz_verlauf WHERE stockwerk_id = ? ORDER BY id DESC LIMIT ?)",
            (stockwerk_id, stockwerk_id, VERLAUF_MAX),
        )

    def knoten_stockwerk(kid: int) -> int:
        return holen("knoten", kid)["stockwerk_id"]

    @app.get("/api/stockwerke/{sid}/verlauf")
    def verlauf(sid: int, _: dict = Depends(ansehen)):
        return db.alle("SELECT id, zeit, benutzer, beschreibung FROM netz_verlauf WHERE stockwerk_id = ? ORDER BY id DESC LIMIT 20", (sid,))

    @app.get("/api/stockwerke/{sid}/stand")
    def stand(sid: int, _: dict = Depends(ansehen)):
        """Letzte Änderung am Stockwerk – die Oberfläche merkt so, wenn jemand anderes gleichzeitig zeichnet."""
        row = db.eins("SELECT id, zeit, benutzer, beschreibung FROM netz_verlauf WHERE stockwerk_id = ? ORDER BY id DESC LIMIT 1", (sid,))
        return row or {"id": 0}

    @app.post("/api/stockwerke/{sid}/rueckgaengig")
    def rueckgaengig(sid: int, ich: dict = Depends(bearbeiten)):
        eintrag = db.eins("SELECT * FROM netz_verlauf WHERE stockwerk_id = ? ORDER BY id DESC LIMIT 1", (sid,))
        if eintrag is None:
            raise fehler(400, "nichts_rueckgaengig")
        if eintrag["benutzer"] and eintrag["benutzer"] != ich["benutzername"]:
            # sonst würde die Arbeit einer anderen Person zurückgenommen
            raise fehler(409, "rueckgaengig_fremd", benutzer=eintrag["benutzer"])
        d = json.loads(eintrag["daten"])
        import sqlite3

        try:
            with db.transaktion() as con:
                con.execute("PRAGMA defer_foreign_keys = ON")
                con.execute("DELETE FROM knoten WHERE stockwerk_id = ?", (sid,))
                con.execute("DELETE FROM flaechen WHERE stockwerk_id = ?", (sid,))
                for f in sorted(d["flaechen"], key=lambda f: f["art"] != "bereich"):
                    con.execute(f"INSERT INTO flaechen ({', '.join(f)}) VALUES ({', '.join('?' * len(f))})", tuple(f.values()))
                for k in d["knoten"]:
                    con.execute(f"INSERT INTO knoten ({', '.join(k)}) VALUES ({', '.join('?' * len(k))})", tuple(k.values()))
                for k in d["kanten"]:
                    if con.execute("SELECT COUNT(*) FROM knoten WHERE id IN (?, ?)", (k["von"], k["nach"])).fetchone()[0] == 2:
                        con.execute(f"INSERT OR REPLACE INTO kanten ({', '.join(k)}) VALUES ({', '.join('?' * len(k))})", tuple(k.values()))
                if "meter_pro_punkt" in d:
                    con.execute("UPDATE stockwerke SET meter_pro_punkt = ? WHERE id = ?", (d["meter_pro_punkt"], sid))
                con.execute("DELETE FROM netz_verlauf WHERE id = ?", (eintrag["id"],))
        except sqlite3.IntegrityError:
            raise fehler(409, "rueckgaengig_nicht_moeglich")
        return {"ok": True, "beschreibung": eintrag["beschreibung"]}

    @app.post("/api/stockwerke/{sid}/ausrichten")
    def ausrichten(sid: int, d: Ausrichten, request: Request, _: dict = Depends(bearbeiten)):
        holen("stockwerke", sid)
        try:
            a, b, c, dd, e, f = transformation([(q.alt_x, q.alt_y, q.neu_x, q.neu_y) for q in d.paare])
        except ValueError as ex:
            raise fehler(400, str(ex))
        merken(sid, request, "ausrichten")
        massstab = math.sqrt(abs(a * e - b * dd)) or 1.0
        with db.transaktion() as con:
            for k in con.execute("SELECT id, x, y FROM knoten WHERE stockwerk_id = ?", (sid,)).fetchall():
                con.execute("UPDATE knoten SET x = ?, y = ? WHERE id = ?", (a * k["x"] + b * k["y"] + c, dd * k["x"] + e * k["y"] + f, k["id"]))
            for fl in con.execute("SELECT id, punkte FROM flaechen WHERE stockwerk_id = ?", (sid,)).fetchall():
                pp = [[a * x + b * y + c, dd * x + e * y + f] for x, y in json.loads(fl["punkte"])]
                con.execute("UPDATE flaechen SET punkte = ? WHERE id = ?", (json.dumps(pp), fl["id"]))
            con.execute("UPDATE stockwerke SET meter_pro_punkt = meter_pro_punkt / ? WHERE id = ?", (massstab, sid))
        knoten_zuordnen(sid)
        return {"ok": True, "massstab": massstab}

    # ---------------------------------------------------------------- Flächen
    def flaeche_pruefen(art: str | None, punkte, farbe: str | None) -> None:
        if art is not None and art not in ("bereich", "raum"):
            raise fehler(400, "art_ungueltig")
        if punkte is not None and len(punkte) < 3:
            raise fehler(400, "zu_wenige_punkte")
        if farbe is not None:
            farbe_pruefen(farbe)

    def passender_bereich(stockwerk_id: int, punkte: list, ohne: int | None = None) -> int | None:
        """Kleinster Bereich, in dem der Schwerpunkt der Fläche liegt."""
        cx = sum(p[0] for p in punkte) / len(punkte)
        cy = sum(p[1] for p in punkte) / len(punkte)
        beste = None
        for b in db.alle("SELECT id, punkte FROM flaechen WHERE stockwerk_id = ? AND art = 'bereich'", (stockwerk_id,)):
            if b["id"] == ohne:
                continue
            pp = json.loads(b["punkte"])
            if im_polygon(cx, cy, pp):
                inhalt = flaeche_inhalt(pp)
                if beste is None or inhalt < beste[0]:
                    beste = (inhalt, b["id"])
        return beste[1] if beste else None

    @app.post("/api/flaechen")
    def flaeche_anlegen(d: Flaeche, request: Request, _: dict = Depends(bearbeiten)):
        holen("stockwerke", d.stockwerk_id)
        flaeche_pruefen(d.art, d.punkte, d.farbe)
        merken(d.stockwerk_id, request, "flaeche_neu")
        punkte = [list(p) for p in d.punkte]
        parent = d.parent_id if d.parent_id is not None else (passender_bereich(d.stockwerk_id, punkte) if d.art == "raum" else None)
        fid = db.ausfuehren(
            "INSERT INTO flaechen (stockwerk_id, parent_id, art, name, nummer, farbe, punkte) VALUES (?,?,?,?,?,?,?)",
            (d.stockwerk_id, parent, d.art, d.name.strip(), d.nummer.strip(), d.farbe, json.dumps(punkte)))
        knoten_zuordnen(d.stockwerk_id)
        return {"id": fid, "parent_id": parent}

    @app.put("/api/flaechen/{fid}")
    def flaeche_aendern(fid: int, d: FlaecheAenderung, request: Request, _: dict = Depends(bearbeiten)):
        f = holen("flaechen", fid)
        flaeche_pruefen(d.art, d.punkte, d.farbe)
        merken(f["stockwerk_id"], request, "flaeche_geaendert")
        felder = d.model_dump(exclude_unset=True)
        if "punkte" in felder:
            felder["punkte"] = json.dumps([list(p) for p in d.punkte])
        if "parent_id" in felder and felder["parent_id"] == fid:
            raise fehler(400, "parent_ungueltig")
        if not felder:
            return {"ok": True}
        sets = ", ".join(f"{k} = ?" for k in felder)
        db.ausfuehren(f"UPDATE flaechen SET {sets} WHERE id = ?", (*[v.strip() if isinstance(v, str) and k in ('name', 'nummer') else v for k, v in felder.items()], fid))
        knoten_zuordnen(f["stockwerk_id"])
        return {"ok": True}

    @app.delete("/api/flaechen/{fid}")
    def flaeche_loeschen(fid: int, request: Request, _: dict = Depends(bearbeiten)):
        f = holen("flaechen", fid)
        merken(f["stockwerk_id"], request, "flaeche_geloescht")
        db.ausfuehren("DELETE FROM flaechen WHERE id = ?", (fid,))
        knoten_zuordnen(f["stockwerk_id"])
        return {"ok": True}

    def knoten_zuordnen(stockwerk_id: int) -> None:
        """Jeder Knoten bekommt die kleinste Fläche (Raum vor Bereich), in der er liegt."""
        flaechen = [(f["id"], f["art"], json.loads(f["punkte"])) for f in db.alle("SELECT id, art, punkte FROM flaechen WHERE stockwerk_id = ?", (stockwerk_id,))]
        flaechen.sort(key=lambda f: (f[1] != "raum", flaeche_inhalt(f[2])))
        with db.transaktion() as con:
            for k in con.execute("SELECT id, x, y, flaeche_id FROM knoten WHERE stockwerk_id = ?", (stockwerk_id,)).fetchall():
                fid = next((f[0] for f in flaechen if im_polygon(k["x"], k["y"], f[2])), None)
                if fid != k["flaeche_id"]:
                    con.execute("UPDATE knoten SET flaeche_id = ? WHERE id = ?", (fid, k["id"]))

    # ---------------------------------------------------------------- Knoten & Kanten
    def knoten_pruefen(art: str | None, aufzug_id: int | None) -> None:
        if art is not None and art not in KNOTEN_ARTEN:
            raise fehler(400, "art_ungueltig")
        if aufzug_id is not None:
            holen("aufzuege", aufzug_id)

    @app.get("/api/stockwerke/{sid}/netz")
    def netz_lesen(sid: int, _: dict = Depends(ansehen)):
        holen("stockwerke", sid)
        flaechen = db.alle("SELECT * FROM flaechen WHERE stockwerk_id = ? ORDER BY art, name", (sid,))
        for f in flaechen:
            f["punkte"] = json.loads(f["punkte"])
        knoten = db.alle("SELECT * FROM knoten WHERE stockwerk_id = ?", (sid,))
        ids = {k["id"] for k in knoten}
        kanten = db.alle(
            """SELECT k.*, a.stockwerk_id AS von_stockwerk, b.stockwerk_id AS nach_stockwerk
                 FROM kanten k JOIN knoten a ON a.id = k.von JOIN knoten b ON b.id = k.nach
                WHERE a.stockwerk_id = ? OR b.stockwerk_id = ?""",
            (sid, sid),
        )
        fremd = set()
        for k in kanten:
            k["gesperrt"] = json.loads(k["gesperrt"])
            for n in (k["von"], k["nach"]):
                if n not in ids:
                    fremd.add(n)
        andere = []
        if fremd:
            platz = ",".join("?" * len(fremd))
            andere = db.alle(
                f"""SELECT k.id, k.name, k.art, s.name AS stockwerk, g.name AS gebaeudeteil, k.stockwerk_id
                      FROM knoten k JOIN stockwerke s ON s.id = k.stockwerk_id JOIN gebaeudeteile g ON g.id = s.gebaeudeteil_id
                     WHERE k.id IN ({platz})""",
                tuple(fremd),
            )
        return {"flaechen": flaechen, "knoten": knoten, "kanten": kanten, "fremde_knoten": andere}

    @app.get("/api/punkte")
    def punkte(_: dict | None = Depends(ansehen)):
        """Alle benannten Knoten (Start, Ziel, Aufzug …) für Auswahllisten."""
        return db.alle(
            """SELECT k.id, k.name, k.art, k.stockwerk_id, k.aufzug_id, k.kapazitaet, s.name AS stockwerk, s.ebene,
                      g.id AS gebaeudeteil_id, g.name AS gebaeudeteil, g.kuerzel, f.name AS flaeche, f.nummer
                 FROM knoten k JOIN stockwerke s ON s.id = k.stockwerk_id
                 JOIN gebaeudeteile g ON g.id = s.gebaeudeteil_id
                 LEFT JOIN flaechen f ON f.id = k.flaeche_id
                WHERE (k.art <> 'weg' OR k.name <> '') AND g.standort_id = ?
                ORDER BY g.reihenfolge, g.name, s.ebene DESC, k.name""",
            (ort(),),
        )

    @app.get("/api/engstellen")
    def engstellen(_: dict = Depends(ansehen)):
        """Benannte Wegstücke und Wegstücke mit Kapazität (für Szenarien: sperren)."""
        return db.alle(
            """SELECT e.id, e.name, e.kapazitaet, a.name AS von_name, b.name AS nach_name, s.name AS stockwerk, g.kuerzel, g.name AS gebaeudeteil
                 FROM kanten e JOIN knoten a ON a.id = e.von JOIN knoten b ON b.id = e.nach
                 JOIN stockwerke s ON s.id = a.stockwerk_id JOIN gebaeudeteile g ON g.id = s.gebaeudeteil_id
                WHERE (e.name <> '' OR e.kapazitaet IS NOT NULL) AND g.standort_id = ?
                ORDER BY g.reihenfolge, s.ebene DESC, e.name""",
            (ort(),),
        )

    @app.post("/api/knoten")
    def knoten_anlegen(d: Knoten, request: Request, _: dict = Depends(bearbeiten)):
        holen("stockwerke", d.stockwerk_id)
        knoten_pruefen(d.art, d.aufzug_id)
        merken(d.stockwerk_id, request, "punkt_neu" if d.art != "weg" else "weg")
        kid = db.ausfuehren(
            "INSERT INTO knoten (stockwerk_id, x, y, art, name, aufzug_id, kapazitaet, minuten_je_einheit, minuten_je_einheit_bis) VALUES (?,?,?,?,?,?,?,?,?)",
            (d.stockwerk_id, d.x, d.y, d.art, d.name.strip(), d.aufzug_id, d.kapazitaet, d.minuten_je_einheit or None, d.minuten_je_einheit_bis or None))
        knoten_zuordnen(d.stockwerk_id)
        return {"id": kid}

    @app.post("/api/knoten/{kid}/vereinen")
    def knoten_vereinen(kid: int, d: Vereinen, request: Request, _: dict = Depends(bearbeiten)):
        """Zwei Punkte zu einem machen (Punkt auf Punkt gezogen). Ein Streckenpunkt geht im anderen auf."""
        a, b = holen("knoten", kid), holen("knoten", d.mit)
        if a["id"] == b["id"] or a["stockwerk_id"] != b["stockwerk_id"]:
            raise fehler(400, "kante_ungueltig")
        if a["art"] != "weg" and b["art"] != "weg":
            raise fehler(409, "beide_benannt")
        bleibt, weg = (a, b) if a["art"] != "weg" else (b, a)
        merken(a["stockwerk_id"], request, "punkt_geaendert")
        with db.transaktion() as con:
            vorhanden = {frozenset((r["von"], r["nach"])) for r in con.execute("SELECT von, nach FROM kanten WHERE von = ? OR nach = ?", (bleibt["id"], bleibt["id"]))}
            for e in con.execute("SELECT * FROM kanten WHERE von = ? OR nach = ?", (weg["id"], weg["id"])).fetchall():
                von = bleibt["id"] if e["von"] == weg["id"] else e["von"]
                nach = bleibt["id"] if e["nach"] == weg["id"] else e["nach"]
                paar = frozenset((von, nach))
                if von == nach or paar in vorhanden:
                    con.execute("DELETE FROM kanten WHERE id = ?", (e["id"],))
                else:
                    con.execute("UPDATE kanten SET von = ?, nach = ? WHERE id = ?", (von, nach, e["id"]))
                    vorhanden.add(paar)
            con.execute("DELETE FROM knoten WHERE id = ?", (weg["id"],))
        return {"id": bleibt["id"]}

    @app.put("/api/knoten/{kid}")
    def knoten_aendern(kid: int, d: KnotenAenderung, request: Request, _: dict = Depends(bearbeiten)):
        k = holen("knoten", kid)
        felder = d.model_dump(exclude_unset=True)
        knoten_pruefen(felder.get("art"), felder.get("aufzug_id"))
        merken(k["stockwerk_id"], request, "punkt_verschoben" if set(felder) <= {"x", "y"} else "punkt_geaendert")
        if "ohne_hinweis" in felder:
            felder["ohne_hinweis"] = int(bool(felder["ohne_hinweis"]))
        if felder.get("kapazitaet") == 0:
            felder["kapazitaet"] = None
        for feld in ("minuten_je_einheit", "minuten_je_einheit_bis"):
            if felder.get(feld) == 0:
                felder[feld] = None
        if "name" in felder:
            felder["name"] = felder["name"].strip()
        if felder:
            sets = ", ".join(f"{f} = ?" for f in felder)
            db.ausfuehren(f"UPDATE knoten SET {sets} WHERE id = ?", (*felder.values(), kid))
        if "x" in felder or "y" in felder:
            knoten_zuordnen(k["stockwerk_id"])
        return {"ok": True}

    @app.delete("/api/knoten/{kid}")
    def knoten_loeschen(kid: int, request: Request, _: dict = Depends(bearbeiten)):
        k_alt = holen("knoten", kid)
        if db.eins("SELECT 1 FROM lieferungen WHERE start_id = ? OR ziel_id = ?", (kid, kid)) or any(
            kid in json.loads(l["via"]) or json.loads(l["rueckweg"]).get("ziel_id") == kid for l in db.alle("SELECT via, rueckweg FROM lieferungen")
        ):
            raise fehler(409, "knoten_in_verwendung")
        merken(k_alt["stockwerk_id"], request, "punkt_geloescht")
        db.ausfuehren("DELETE FROM knoten WHERE id = ?", (kid,))
        return {"ok": True}

    def kante_pruefen(von: dict, nach: dict, laenge_m: float | None, gesperrt: list[int] | None) -> None:
        if von["id"] == nach["id"]:
            raise fehler(400, "kante_ungueltig")
        if von["stockwerk_id"] != nach["stockwerk_id"] and not laenge_m:
            raise fehler(400, "laenge_noetig")
        if gesperrt:
            ids = {t["id"] for t in db.alle("SELECT id FROM transportarten")}
            if not set(gesperrt) <= ids:
                raise fehler(400, "transportart_unbekannt")

    @app.post("/api/kanten")
    def kante_anlegen(d: Kante, request: Request, _: dict = Depends(bearbeiten)):
        von, nach = holen("knoten", d.von), holen("knoten", d.nach)
        kante_pruefen(von, nach, d.laenge_m, d.gesperrt)
        vorhanden = db.eins("SELECT id FROM kanten WHERE (von = ? AND nach = ?) OR (von = ? AND nach = ?)", (d.von, d.nach, d.nach, d.von))
        if vorhanden:
            return {"id": vorhanden["id"]}
        merken(von["stockwerk_id"], request, "weg")
        return {"id": db.ausfuehren(
            "INSERT INTO kanten (von, nach, laenge_m, kapazitaet, gesperrt, name) VALUES (?,?,?,?,?,?)",
            (d.von, d.nach, d.laenge_m, d.kapazitaet, json.dumps(sorted(set(d.gesperrt))), d.name.strip()))}

    @app.put("/api/kanten/{kid}")
    def kante_aendern(kid: int, d: KanteAenderung, request: Request, _: dict = Depends(bearbeiten)):
        k = holen("kanten", kid)
        felder = d.model_dump(exclude_unset=True)
        von, nach = holen("knoten", k["von"]), holen("knoten", k["nach"])
        laenge = felder.get("laenge_m", k["laenge_m"]) or None
        kante_pruefen(von, nach, laenge, felder.get("gesperrt"))
        merken(von["stockwerk_id"], request, "weg_geaendert")
        if "laenge_m" in felder:
            felder["laenge_m"] = laenge
        if felder.get("kapazitaet") == 0:
            felder["kapazitaet"] = None
        if "gesperrt" in felder:
            felder["gesperrt"] = json.dumps(sorted(set(felder["gesperrt"])))
        if "name" in felder:
            felder["name"] = felder["name"].strip()
        if felder:
            sets = ", ".join(f"{f} = ?" for f in felder)
            db.ausfuehren(f"UPDATE kanten SET {sets} WHERE id = ?", (*felder.values(), kid))
        return {"ok": True}

    @app.delete("/api/kanten/{kid}")
    def kante_loeschen(kid: int, request: Request, _: dict = Depends(bearbeiten)):
        k = holen("kanten", kid)
        merken(knoten_stockwerk(k["von"]), request, "weg_geloescht")
        with db.transaktion() as con:
            con.execute("DELETE FROM kanten WHERE id = ?", (kid,))
            # Zwischenpunkte, die jetzt an nichts mehr hängen, mit wegräumen (benannte Punkte bleiben)
            for nid in (k["von"], k["nach"]):
                con.execute(
                    """DELETE FROM knoten WHERE id = ? AND art = 'weg'
                         AND NOT EXISTS (SELECT 1 FROM kanten WHERE von = ? OR nach = ?)""",
                    (nid, nid, nid),
                )
        return {"ok": True}

    @app.post("/api/kanten/{kid}/teilen")
    def kante_teilen(kid: int, d: Teilen, request: Request, _: dict = Depends(bearbeiten)):
        """Setzt einen neuen Wegknoten auf die Kante (nächster Punkt zu x/y) und teilt sie."""
        k = holen("kanten", kid)
        a, b = holen("knoten", k["von"]), holen("knoten", k["nach"])
        if a["stockwerk_id"] != b["stockwerk_id"]:
            raise fehler(400, "kante_ungueltig")
        merken(a["stockwerk_id"], request, "weg")
        dx, dy = b["x"] - a["x"], b["y"] - a["y"]
        l2 = dx * dx + dy * dy or 1.0
        t = min(1.0, max(0.0, ((d.x - a["x"]) * dx + (d.y - a["y"]) * dy) / l2))
        x, y = a["x"] + t * dx, a["y"] + t * dy
        with db.transaktion() as con:
            nid = con.execute("INSERT INTO knoten (stockwerk_id, x, y, art) VALUES (?, ?, ?, 'weg')", (a["stockwerk_id"], x, y)).lastrowid
            con.execute("DELETE FROM kanten WHERE id = ?", (kid,))
            anteile = ((a["id"], t), (b["id"], 1 - t))
            for nachbar, anteil in anteile:
                laenge = k["laenge_m"] * anteil if k["laenge_m"] else None
                con.execute(
                    "INSERT INTO kanten (von, nach, laenge_m, kapazitaet, gesperrt, name) VALUES (?,?,?,?,?,?)",
                    (nachbar, nid, laenge, k["kapazitaet"], k["gesperrt"], k["name"]))
        knoten_zuordnen(a["stockwerk_id"])
        return {"id": nid, "x": x, "y": y}

    # ---------------------------------------------------------------- Lieferungen
    def lieferung_lesen(row: dict) -> dict:
        for k in ("ladung", "via", "regel", "rueckweg"):
            row[k] = json.loads(row[k])
        row["aktiv"] = bool(row["aktiv"])
        return row

    def knoten_name(kid: int) -> str:
        k = db.eins("SELECT k.name, k.art, a.name AS aufzug FROM knoten k LEFT JOIN aufzuege a ON a.id = k.aufzug_id WHERE k.id = ?", (kid,))
        return (k["name"] or k["aufzug"] or f"#{kid}") if k else f"#{kid}"

    def transportart_waehlen(d: Lieferung) -> int:
        """Erste Transportart (nach Reihenfolge der Stammdaten), die hin und zurück einen Weg findet."""
        arten = db.alle("SELECT * FROM transportarten WHERE standort_id = ? ORDER BY id", (ort(),))
        if not arten:
            raise fehler(400, "transportart_fehlt")
        netz = Netz(db)
        rueck_ziel = d.rueckweg.ziel_id or d.start_id
        for ta in arten:
            try:
                netz.weg(d.start_id, d.ziel_id, ta, d.via)
                if d.rueckweg.modus != "keiner":
                    netz.weg(d.ziel_id, rueck_ziel, ta, [])
                return ta["id"]
            except WegFehler:
                continue
        return arten[0]["id"]  # noch kein Weg: „Erste Schritte“ zeigt, woran es liegt

    def lieferung_pruefen(d: Lieferung) -> dict:
        if d.richtung not in RICHTUNGEN:
            raise fehler(400, "richtung_ungueltig")
        for z in (d.uhrzeit, d.spaetestens, d.rueckweg.uhrzeit):
            if z and not UHRZEIT.match(z):
                raise fehler(400, "uhrzeit_ungueltig")
        for kid in [d.start_id, d.ziel_id, *d.via, *([d.rueckweg.ziel_id] if d.rueckweg.ziel_id else [])]:
            holen("knoten", kid)
        if d.start_id == d.ziel_id:
            raise fehler(400, "start_gleich_ziel")
        if d.transportart_id is None:
            d.transportart_id = transportart_waehlen(d)
        holen("transportarten", d.transportart_id)
        if not d.name.strip():
            d.name = f"{knoten_name(d.start_id)} → {knoten_name(d.ziel_id)}"[:150]
        wt = {w["id"] for w in db.alle("SELECT id FROM wagentypen WHERE standort_id = ?", (ort(),))}
        if any(p.wagentyp_id not in wt for p in d.ladung):
            raise fehler(400, "wagentyp_unbekannt")
        if d.rueckweg.modus not in RUECKWEG_MODI:
            raise fehler(400, "rueckweg_ungueltig")
        if d.rueckweg.modus == "spaeter" and not d.rueckweg.uhrzeit:
            raise fehler(400, "rueckweg_uhrzeit_fehlt")
        try:
            regel = normalisieren(d.regel)
        except RegelFehler as e:
            raise fehler(400, "regel_ungueltig", feld=str(e))
        return {
            "name": d.name.strip(), "lieferant": d.lieferant.strip(), "richtung": d.richtung,
            "transportart_id": d.transportart_id, "start_id": d.start_id, "ziel_id": d.ziel_id,
            "uhrzeit": d.uhrzeit, "spaetestens": d.spaetestens or None, "streuung": d.streuung,
            "ladung": json.dumps([p.model_dump() for p in d.ladung if p.anzahl > 0]),
            "via": json.dumps(d.via), "regel": json.dumps(regel), "rueckweg": json.dumps(d.rueckweg.model_dump()),
            "aktiv": int(d.aktiv), "notiz": d.notiz,
        }

    @app.get("/api/lieferungen")
    def lieferungen(_: dict = Depends(ansehen)):
        return [lieferung_lesen(r) for r in db.alle("SELECT * FROM lieferungen WHERE standort_id = ? ORDER BY uhrzeit, name", (ort(),))]

    @app.post("/api/lieferungen")
    def lieferung_anlegen(d: Lieferung, _: dict = Depends(lieferungen_recht)):
        werte = {**lieferung_pruefen(d), "standort_id": ort()}
        sp = ", ".join(werte)
        lid = db.ausfuehren(f"INSERT INTO lieferungen ({sp}) VALUES ({', '.join('?' * len(werte))})", tuple(werte.values()))
        ta = holen("transportarten", werte["transportart_id"])
        try:
            weg = Netz(db).weg(werte["start_id"], werte["ziel_id"], ta, json.loads(werte["via"]))
            weg_info = {"weg_ok": True, "dauer": round(weg.dauer, 1)}
        except WegFehler as e:
            weg_info = {"weg_ok": False, "code": e.code}
        return {"id": lid, "name": werte["name"], "transportart": ta["name"], **weg_info}

    @app.put("/api/lieferungen/{lid}")
    def lieferung_aendern(lid: int, d: Lieferung, _: dict = Depends(lieferungen_recht)):
        holen("lieferungen", lid)
        werte = lieferung_pruefen(d)
        sets = ", ".join(f"{k} = ?" for k in werte)
        db.ausfuehren(f"UPDATE lieferungen SET {sets} WHERE id = ?", (*werte.values(), lid))
        return {"ok": True}

    @app.delete("/api/lieferungen/{lid}")
    def lieferung_loeschen(lid: int, _: dict = Depends(lieferungen_recht)):
        db.ausfuehren("DELETE FROM lieferungen WHERE id = ?", (lid,))
        return {"ok": True}

    @app.get("/api/lieferungen/{lid}/weg")
    def lieferung_weg(lid: int, _: dict = Depends(ansehen)):
        l = lieferung_lesen(holen("lieferungen", lid))
        netz = Netz(db)
        ta = holen("transportarten", l["transportart_id"])
        try:
            weg = netz.weg(l["start_id"], l["ziel_id"], ta, l["via"])
        except WegFehler as e:
            raise fehler(422, e.code, **e.extra)
        return {
            "dauer": round(weg.dauer, 1),
            "laenge_m": round(weg.laenge_m, 1),
            "knoten": [
                {"id": k, "stockwerk_id": netz.knoten[k]["stockwerk_id"], "x": netz.knoten[k]["x"], "y": netz.knoten[k]["y"]}
                for k in weg.knoten
            ],
            "abschnitte": [a.als_dict() for a in weg.abschnitte],
        }

    # ---------------------------------------------------------------- Simulation
    def ist_feiertag_fn():
        bl = db.ort_einstellung("bundesland", db.einstellung("bundesland", "NW"))
        sid = ort()
        sonder = {s["datum"] for s in db.alle("SELECT datum FROM sondertage WHERE standort_id = ?", (sid,))}
        cache: dict[int, set] = {}

        def pruefen(tag: date) -> tuple[bool, str | None]:
            if tag.year not in cache:
                cache[tag.year] = {d.isoformat(): k for d, k in feiertage(tag.year, bl)}
            iso = tag.isoformat()
            if iso in cache[tag.year]:
                return True, cache[tag.year][iso]
            if iso in sonder:
                return True, db.eins("SELECT name FROM sondertage WHERE datum = ? AND standort_id = ?", (iso, sid))["name"]
            return False, None

        return pruefen

    def szenario_laden(szenario: int | None) -> dict:
        if not szenario:
            return {}
        row = db.eins("SELECT aenderungen FROM szenarien WHERE id = ? AND standort_id = ?", (szenario, ort()))
        if row is None:
            raise fehler(404, "nicht_gefunden")
        return json.loads(row["aenderungen"])

    def tag_vorbereiten(tag: date, aenderungen: dict, pruefen=None) -> dict:
        """Lädt alles für einen Tag einmal; tag_rechnen kann damit beliebig oft (mit Zufall) rechnen."""
        pruefen = pruefen or ist_feiertag_fn()
        feiertag, feiertag_name = pruefen(tag)
        alle = [lieferung_lesen(r) for r in db.alle("SELECT * FROM lieferungen WHERE standort_id = ? ORDER BY uhrzeit, id", (ort(),))]
        sd = stammdaten()
        netz = Netz(db)
        szenario_anwenden(aenderungen, alle, sd, netz)
        heute = sorted((l for l in alle if l["aktiv"] and gilt_am(l["regel"], tag, feiertag)), key=lambda l: (l["uhrzeit"], l["id"]))
        # späte Lieferungen des Vortags, die über Mitternacht laufen können
        vortag = date.fromordinal(tag.toordinal() - 1)
        vortag_feiertag, _ = pruefen(vortag)
        vom_vortag = [l for l in alle if (l["uhrzeit"] >= VORTAG_AB or ((l["rueckweg"] or {}).get("uhrzeit") or "") >= VORTAG_AB)
                      and l["aktiv"] and gilt_am(l["regel"], vortag, vortag_feiertag)]
        return {"tag": tag, "feiertag": feiertag_name, "heute": heute, "vortag": vom_vortag, "sd": sd, "netz": netz}

    def tag_rechnen(v: dict, zufall: random.Random | None = None) -> dict:
        sd, tag = v["sd"], v["tag"]
        sim = Simulation(v["netz"], {t["id"]: t for t in sd["transportarten"]}, {w["id"]: w for w in sd["wagentypen"]}, tag.isoweekday(), zufall)
        for l in v["vortag"]:
            sim.lieferung_einplanen(l, vortag=True)
        for l in v["heute"]:
            sim.lieferung_einplanen(l)
        ergebnis = sim.laufen()
        ergebnis.update({"datum": tag.isoformat(), "feiertag": v["feiertag"], "wochentag": tag.isoweekday(), "lieferungen": [l["id"] for l in v["heute"]]})
        return ergebnis

    def tag_simulieren(tag: date, aenderungen: dict, pruefen=None) -> dict:
        return tag_rechnen(tag_vorbereiten(tag, aenderungen, pruefen))

    def tag_lesen(datum: str | None) -> date:
        try:
            return date.fromisoformat(datum) if datum else date.today()
        except ValueError:
            raise fehler(400, "datum_ungueltig")

    @app.get("/api/simulation")
    def simulation(datum: str | None = None, szenario: int | None = None, _: dict = Depends(ansehen)):
        ergebnis = tag_simulieren(tag_lesen(datum), szenario_laden(szenario))
        ergebnis["szenario"] = szenario
        return ergebnis

    # ---------------------------------------------------------------- Streuung (viele Tage mit Zufall)
    def quantil(werte: list[float], q: float) -> float:
        if not werte:
            return 0.0
        w = sorted(werte)
        return w[min(len(w) - 1, int(q * len(w)))]

    def streuung_auswerten(ergebnisse: list[dict], schwelle: float) -> dict:
        n = len(ergebnisse)
        ressourcen: dict[tuple, dict] = {}
        lieferungen: dict[int, dict] = {}
        tage_ueber = 0
        for e in ergebnisse:
            for r in e["ressourcen"]:
                x = ressourcen.setdefault((r["typ"], r["id"]), {"typ": r["typ"], "id": r["id"], "name": r["name"], "stockwerk_id": r["stockwerk_id"], "warte": [], "spitze": []})
                x["warte"].append(r["max_wartezeit"])
                x["spitze"].append(r["spitze"])
            je_lieferung: dict[int, dict] = {}
            for f in e["fahrten"]:
                if f["vortag"]:
                    continue
                j = je_lieferung.setdefault(f["lieferung_id"], {"name": f["name"], "verspaetet": False, "warte": 0.0})
                j["verspaetet"] |= f["verspaetet"]
                j["warte"] = max(j["warte"], sum(f["warte"].values()))
            for lid, j in je_lieferung.items():
                x = lieferungen.setdefault(lid, {"id": lid, "name": j["name"], "verspaetet": 0, "warte": []})
                x["verspaetet"] += int(j["verspaetet"])
                x["warte"].append(j["warte"])
            if e["zusammenfassung"]["max_wartezeit"] > schwelle:
                tage_ueber += 1

        def ressource(x):
            warte = x["warte"] + [0.0] * (n - len(x["warte"]))  # an Tagen ohne Nutzung: keine Wartezeit
            return {"typ": x["typ"], "id": x["id"], "name": x["name"], "stockwerk_id": x["stockwerk_id"],
                    "anteil_ueber": round(sum(1 for w in warte if w > schwelle) / n, 3),
                    "median": quantil(warte, 0.5), "p90": quantil(warte, 0.9), "max": max(warte),
                    "spitze_p90": quantil(x["spitze"], 0.9)}

        def lieferung(x):
            return {"id": x["id"], "name": x["name"], "anteil_verspaetet": round(x["verspaetet"] / n, 3),
                    "anteil_ueber": round(sum(1 for w in x["warte"] if w > schwelle) / n, 3),
                    "median": quantil(x["warte"], 0.5), "p90": quantil(x["warte"], 0.9), "max": max(x["warte"], default=0.0)}

        res = sorted((ressource(x) for x in ressourcen.values()), key=lambda r: (r["anteil_ueber"], r["p90"]), reverse=True)
        lief = sorted((lieferung(x) for x in lieferungen.values()), key=lambda r: (r["anteil_verspaetet"], r["anteil_ueber"], r["p90"]), reverse=True)
        return {"laeufe": n, "schwelle": schwelle, "anteil_tage_ueber": round(tage_ueber / n, 3) if n else 0,
                "max_wartezeit_p90": quantil([e["zusammenfassung"]["max_wartezeit"] for e in ergebnisse], 0.9),
                "ressourcen": res, "lieferungen": lief}

    def mehrfach(v: dict, laeufe: int, schritt=None) -> list[dict]:
        ergebnisse = []
        for seed in range(laeufe):
            ergebnisse.append(tag_rechnen(v, random.Random(seed)))
            if schritt:
                schritt()
        return ergebnisse

    def streuung_rechnen(datum: str | None, szenario: int | None, laeufe: int, schwelle: float, fortschritt=None) -> dict:
        laeufe = max(5, min(laeufe, 500))
        v = tag_vorbereiten(tag_lesen(datum), szenario_laden(szenario))
        zaehler = [0]

        def schritt():
            zaehler[0] += 1
            if fortschritt:
                fortschritt(zaehler[0] / laeufe)

        ergebnis = streuung_auswerten(mehrfach(v, laeufe, schritt), schwelle * 60)
        ergebnis.update({"datum": v["tag"].isoformat(), "szenario": szenario})
        return ergebnis

    @app.get("/api/simulation/streuung")
    def streuung(datum: str | None = None, szenario: int | None = None, laeufe: int = 100, schwelle: float = 30,
                 _: dict = Depends(ansehen)):
        """Rechnet den Tag viele Male mit zufälligen Abweichungen (Ankunft, Entladen, Personen im Aufzug)."""
        return streuung_rechnen(datum, szenario, laeufe, schwelle)

    # ---------------------------------------------------------------- Mindestbedarf
    BEDARF_ARTEN = {"transportart": ("transportarten", "fahrzeuge"), "knoten": ("knoten", "knoten"), "kante": ("kanten", "kante")}

    @app.get("/api/simulation/bedarf")
    def bedarf(art: str, id: int, ziel: float = 15, datum: str | None = None, szenario: int | None = None,
               laeufe: int = 0, max_anzahl: int = 20, _: dict = Depends(ansehen)):
        """Kleinste Anzahl (Fahrzeuge/Personen, Tore, gleichzeitig auf einer Engstelle), bei der dort
        niemand länger als ziel Minuten wartet. Mit laeufe > 0 zählt der 90-%-Wert über so viele Tage."""
        return bedarf_rechnen(art, id, ziel, datum, szenario, laeufe, max_anzahl)

    def bedarf_rechnen(art: str, id: int, ziel: float, datum: str | None, szenario: int | None,
                       laeufe: int, max_anzahl: int, fortschritt=None) -> dict:
        if art not in BEDARF_ARTEN:
            raise fehler(400, "art_ungueltig")
        tabelle, typ = BEDARF_ARTEN[art]
        holen(tabelle, id)
        tag = tag_lesen(datum)
        basis = szenario_laden(szenario)
        laeufe = max(0, min(laeufe, 200))
        max_anzahl = max(1, min(max_anzahl, 50))
        punkte, empfehlung = [], None
        for n in range(1, max_anzahl + 1):
            aend = copy.deepcopy(basis)
            werte = {"anzahl": n, "schichten": []} if art == "transportart" else {"kapazitaet": n}
            aend.setdefault(tabelle, {}).setdefault(str(id), {}).update(werte)
            v = tag_vorbereiten(tag, aend)
            ergebnisse = mehrfach(v, laeufe) if laeufe else [tag_rechnen(v)]
            if fortschritt:
                # Wie weit es geht, ist offen (bis zur Empfehlung + 1) – grob nach der Obergrenze schätzen
                fortschritt(min(0.95, n / max(2, min(max_anzahl, (empfehlung or n) + 4))))
            warte = [next((r["max_wartezeit"] for r in e["ressourcen"] if r["typ"] == typ and r["id"] == id), 0.0) for e in ergebnisse]
            spitze = [next((r["spitze"] for r in e["ressourcen"] if r["typ"] == typ and r["id"] == id), 0.0) for e in ergebnisse]
            wert = quantil(warte, 0.9) if laeufe else warte[0]
            punkte.append({"anzahl": n, "wartezeit": round(wert, 1), "auslastung": round(quantil(spitze, 0.9), 3),
                           "verspaetet": round(sum(e["zusammenfassung"]["verspaetet"] for e in ergebnisse) / len(ergebnisse), 1)})
            if empfehlung is None and wert <= ziel * 60:
                empfehlung = n
            if empfehlung is not None and n >= empfehlung + 1:
                break  # eine Stufe mehr zum Vergleich zeigen, dann aufhören
        return {"art": art, "id": id, "ziel": ziel, "laeufe": laeufe, "empfehlung": empfehlung, "punkte": punkte}

    @app.get("/api/simulation/woche")
    def woche(von: str | None = None, szenario: int | None = None, _: dict = Depends(ansehen)):
        start = tag_lesen(von)
        aend = szenario_laden(szenario)
        pruefen = ist_feiertag_fn()
        tage = []
        for i in range(7):
            tag = date.fromordinal(start.toordinal() + i)
            e = tag_simulieren(tag, aend, pruefen)
            stunden = {}
            for f in e["fahrten"]:
                h = int(f["geplant"] // 3600)
                st = stunden.setdefault(h, {"fahrten": 0, "max_warte": 0.0, "warte": 0.0, "verspaetet": 0})
                w = sum(f["warte"].values())
                st["fahrten"] += 1
                st["warte"] += w
                st["max_warte"] = max(st["max_warte"], w)
                st["verspaetet"] += int(f["verspaetet"])
            tage.append({"datum": e["datum"], "wochentag": e["wochentag"], "feiertag": e["feiertag"], "zusammenfassung": e["zusammenfassung"],
                         "stunden": {str(h): v for h, v in sorted(stunden.items())}, "fehler": len(e["fehler"])})
        return {"von": start.isoformat(), "szenario": szenario, "tage": tage}

    # ---------------------------------------------------------------- Rechnungen im Hintergrund
    # Streuung und Mindestbedarf rechnen einen Tag hunderte Male. Ein Zwischenspeicher wie Cloudflare
    # bricht Anfragen nach 100 s ab – deshalb im Hintergrund rechnen, die Seite fragt den Stand ab.
    rechnungen: dict[str, dict] = {}
    rechnungen_sperre = threading.Lock()

    def rechnungen_aufraeumen() -> None:
        jetzt = time.time()
        with rechnungen_sperre:
            for rid, r in list(rechnungen.items()):
                if r["status"] != "laeuft" and jetzt - r["zeit"] > 3600:
                    rechnungen.pop(rid, None)

    @app.post("/api/rechnungen")
    def rechnung_starten(d: RechnungAuftrag, ich: dict = Depends(ansehen)):
        rechnungen_aufraeumen()
        with rechnungen_sperre:
            eigene = [r for r in rechnungen.values() if r["benutzer"] == ich["id"] and r["status"] == "laeuft"]
            for r in eigene:  # neue Rechnung ersetzt eine noch laufende desselben Benutzers
                r["abbruch"] = True
            if sum(1 for r in rechnungen.values() if r["status"] == "laeuft" and not r["abbruch"]) >= 4:
                raise fehler(429, "zu_viele_rechnungen")
            rid = secrets.token_hex(8)
            job = {"benutzer": ich["id"], "status": "laeuft", "fortschritt": 0.0, "ergebnis": None, "fehler": None,
                   "abbruch": False, "zeit": time.time()}
            rechnungen[rid] = job

        class Abgebrochen(Exception):
            pass

        def fortschritt(anteil: float) -> None:
            job["fortschritt"] = round(min(1.0, anteil), 3)
            if job["abbruch"]:
                raise Abgebrochen

        def laufen():
            try:
                p = dict(d.parameter)
                p["szenario"] = int(p["szenario"]) if p.get("szenario") else None
                if d.art == "streuung":
                    e = streuung_rechnen(p.get("datum"), p.get("szenario"), int(p.get("laeufe", 100)), float(p.get("schwelle", 30)), fortschritt)
                else:
                    e = bedarf_rechnen(str(p.get("art", "")), int(p.get("id", 0)), float(p.get("ziel", 15)), p.get("datum"), p.get("szenario"),
                                       int(p.get("laeufe", 0)), int(p.get("max_anzahl", 20)), fortschritt)
                job.update(ergebnis=e, fortschritt=1.0, status="fertig")
            except Abgebrochen:
                job["status"] = "abgebrochen"
            except HTTPException as ex:
                job.update(status="fehler", fehler=ex.detail)
            except (TypeError, ValueError):
                job.update(status="fehler", fehler={"code": "allgemein"})
            except Exception:
                log.exception("Rechnung %s fehlgeschlagen", d.art)
                job.update(status="fehler", fehler={"code": "allgemein"})
            finally:
                job["zeit"] = time.time()

        # Standort und Zugriffsrechte der Anfrage mitnehmen
        kontext = contextvars.copy_context()
        threading.Thread(target=kontext.run, args=(laufen,), daemon=True, name=f"rechnung-{rid}").start()
        return {"id": rid}

    def rechnung_holen(rid: str, ich: dict) -> dict:
        r = rechnungen.get(rid)
        if r is None or r["benutzer"] != ich["id"]:
            raise fehler(404, "nicht_gefunden")
        return r

    @app.get("/api/rechnungen/{rid}")
    def rechnung_stand(rid: str, ich: dict = Depends(ansehen)):
        r = rechnung_holen(rid, ich)
        return {"status": r["status"], "fortschritt": r["fortschritt"], "ergebnis": r["ergebnis"], "fehler": r["fehler"]}

    @app.delete("/api/rechnungen/{rid}")
    def rechnung_abbrechen(rid: str, ich: dict = Depends(ansehen)):
        rechnung_holen(rid, ich)["abbruch"] = True
        return {"ok": True}

    # ---------------------------------------------------------------- Szenarien
    def szenario_lesen(row: dict) -> dict:
        row["aenderungen"] = json.loads(row["aenderungen"])
        return row

    @app.get("/api/szenarien")
    def szenarien(_: dict = Depends(ansehen)):
        return [szenario_lesen(r) for r in db.alle("SELECT * FROM szenarien WHERE standort_id = ? ORDER BY name", (ort(),))]

    def aenderungen_pruefen(a: dict) -> str:
        erlaubt = {"lieferungen", "transportarten", "aufzuege", "kanten", "knoten"}
        if not isinstance(a, dict) or not set(a) <= erlaubt or any(not isinstance(v, dict) for v in a.values()):
            raise fehler(400, "szenario_ungueltig")
        for l in (a.get("lieferungen") or {}).values():
            for z in (l.get("uhrzeit"), l.get("spaetestens")):
                if z and not UHRZEIT.match(z):
                    raise fehler(400, "uhrzeit_ungueltig")
        return json.dumps(a)

    @app.post("/api/szenarien")
    def szenario_anlegen(d: Szenario, _: dict = Depends(lieferungen_recht)):
        return {"id": db.ausfuehren("INSERT INTO szenarien (name, beschreibung, aenderungen, standort_id) VALUES (?, ?, ?, ?)",
                                    (d.name.strip(), d.beschreibung, aenderungen_pruefen(d.aenderungen), ort()))}

    @app.put("/api/szenarien/{sid}")
    def szenario_aendern(sid: int, d: Szenario, _: dict = Depends(lieferungen_recht)):
        holen("szenarien", sid)
        db.ausfuehren("UPDATE szenarien SET name = ?, beschreibung = ?, aenderungen = ? WHERE id = ?",
                      (d.name.strip(), d.beschreibung, aenderungen_pruefen(d.aenderungen), sid))
        return {"ok": True}

    @app.delete("/api/szenarien/{sid}")
    def szenario_loeschen(sid: int, _: dict = Depends(lieferungen_recht)):
        db.ausfuehren("DELETE FROM szenarien WHERE id = ?", (sid,))
        return {"ok": True}

    @app.post("/api/szenarien/{sid}/uebernehmen")
    def szenario_uebernehmen(sid: int, _: dict = Depends(lieferungen_recht)):
        """Übernimmt die geänderten Lieferungen eines Szenarios in den Ist-Zustand."""
        a = szenario_lesen(holen("szenarien", sid))["aenderungen"]
        n = 0
        with db.transaktion() as con:
            for lid, werte in (a.get("lieferungen") or {}).items():
                for k, v in werte.items():
                    if k in ("uhrzeit", "spaetestens", "aktiv", "transportart_id"):
                        con.execute(f"UPDATE lieferungen SET {k} = ? WHERE id = ?", (int(v) if k == "aktiv" else v, int(lid)))
                    elif k in ("ladung", "rueckweg", "via"):
                        con.execute(f"UPDATE lieferungen SET {k} = ? WHERE id = ?", (json.dumps(v), int(lid)))
                n += 1
        return {"ok": True, "lieferungen": n}

    # ---------------------------------------------------------------- Import & Export
    def export_kontext():
        return {"punkte": punkte(None), "stamm": stammdaten(), "lieferungen": [lieferung_lesen(r) for r in db.alle("SELECT * FROM lieferungen WHERE standort_id = ? ORDER BY uhrzeit, name", (ort(),))]}

    def datei_antwort(daten: bytes, name: str, art: str) -> Response:
        # Umlaute & Co. im Namen (z. B. Stockwerk „Süd“) als filename* – im Kopf sind nur einfache Zeichen erlaubt
        einfach = re.sub(r'[^A-Za-z0-9._-]', "_", name)
        return Response(daten, media_type=art, headers={
            "Content-Disposition": f"attachment; filename=\"{einfach}\"; filename*=UTF-8''{quote(name)}"})

    XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

    @app.get("/api/export/lieferungen.xlsx")
    def lieferungen_export(_: dict = Depends(ansehen)):
        return datei_antwort(export.lieferungen_xlsx(**export_kontext()), f"lieferungen-{date.today()}.xlsx", XLSX)

    @app.post("/api/import/lieferungen")
    async def lieferungen_import(datei: UploadFile = File(...), pruefen: bool = True, _: dict = Depends(lieferungen_recht)):
        inhalt = await datei.read()
        if len(inhalt) > 20 * 1024 * 1024:
            raise fehler(413, "datei_zu_gross")
        try:
            zeilen = export.lieferungen_lesen(inhalt, datei.filename or "")
        except export.ImportFehler as ex:
            raise fehler(400, ex.code)
        kontext = export_kontext()
        ergebnis = export.lieferungen_zuordnen(zeilen, kontext)
        if not pruefen and not any(z["fehler"] for z in ergebnis):
            for z in ergebnis:
                if "streuung" not in z["daten"] and z.get("id"):
                    alt = db.eins("SELECT streuung FROM lieferungen WHERE id = ? AND standort_id = ?", (z["id"], ort()))
                    if alt:
                        z["daten"]["streuung"] = alt["streuung"]
                try:
                    werte = lieferung_pruefen(Lieferung(**z["daten"]))
                except Exception as ex:  # fachliche Prüfung wie beim Speichern im Dialog
                    detail = getattr(ex, "detail", {"code": "allgemein"})
                    z["fehler"].append(detail.get("code", "allgemein") if isinstance(detail, dict) else "allgemein")
                    continue
                if z.get("id") and db.eins("SELECT 1 FROM lieferungen WHERE id = ? AND standort_id = ?", (z["id"], ort())):
                    sets = ", ".join(f"{k} = ?" for k in werte)
                    db.ausfuehren(f"UPDATE lieferungen SET {sets} WHERE id = ?", (*werte.values(), z["id"]))
                    z["aktion"] = "geaendert"
                else:
                    werte["standort_id"] = ort()
                    z["id"] = db.ausfuehren(f"INSERT INTO lieferungen ({', '.join(werte)}) VALUES ({', '.join('?' * len(werte))})", tuple(werte.values()))
                    z["aktion"] = "neu"
        uebernommen = (not pruefen) and all(not z["fehler"] for z in ergebnis)
        return {"zeilen": [{k: v for k, v in z.items() if k != "daten"} for z in ergebnis], "uebernommen": uebernommen}

    @app.get("/api/export/auswertung.xlsx")
    def auswertung_export(datum: str | None = None, szenario: int | None = None, _: dict = Depends(ansehen)):
        tag = tag_lesen(datum)
        e = tag_simulieren(tag, szenario_laden(szenario))
        name = db.eins("SELECT name FROM szenarien WHERE id = ?", (szenario,))["name"] if szenario else None
        return datei_antwort(export.auswertung_xlsx(e, export_kontext(), name), f"auswertung-{tag}.xlsx", XLSX)

    @app.get("/api/export/karte/{sid}.pdf")
    def karte_export(sid: int, datum: str | None = None, von: str = "00:00", bis: str = "23:59", szenario: int | None = None,
                     start: int | None = None, _: dict = Depends(ansehen)):
        s_ = holen("stockwerke", sid)
        if not s_["plan_id"]:
            raise fehler(400, "kein_plan")
        if not UHRZEIT.match(von) or not UHRZEIT.match(bis):
            raise fehler(400, "uhrzeit_ungueltig")
        tag = tag_lesen(datum)
        e = tag_simulieren(tag, szenario_laden(szenario))
        szenario_name = db.eins("SELECT name FROM szenarien WHERE id = ?", (szenario,))["name"] if szenario else None
        pdf = export.karte_pdf(db, pfade, sid, e, von, bis, start, szenario_name, export_kontext())
        return datei_antwort(pdf, f"karte-{s_['name']}-{tag}.pdf".replace(" ", "_"), "application/pdf")

    @app.get("/api/kalender")
    def kalender(von: str, tage: int = 14, _: dict = Depends(ansehen)):
        """Welche Lieferungen an den nächsten Tagen stattfinden (für die Vorschau der Regeln)."""
        try:
            start = date.fromisoformat(von)
        except ValueError:
            raise fehler(400, "datum_ungueltig")
        tage = max(1, min(tage, 62))
        pruefen = ist_feiertag_fn()
        alle = [lieferung_lesen(r) for r in db.alle("SELECT id, regel, aktiv, ladung, via, rueckweg FROM lieferungen WHERE standort_id = ?", (ort(),))]
        ergebnis = []
        for i in range(tage):
            tag = date.fromordinal(start.toordinal() + i)
            ft, name = pruefen(tag)
            ergebnis.append({
                "datum": tag.isoformat(), "feiertag": name,
                "lieferungen": [l["id"] for l in alle if l["aktiv"] and gilt_am(l["regel"], tag, ft)],
            })
        return ergebnis

