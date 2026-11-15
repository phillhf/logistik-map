"""Schnittstellen für Flächen, Wegenetz, Stammdaten, Lieferungen und Ablauf-Simulation."""

from __future__ import annotations

import json
import re
from datetime import date

from fastapi import Depends, FastAPI
from pydantic import BaseModel, Field

from .db import Datenbank
from .feiertage import feiertage
from .netz import KNOTEN_ARTEN, Netz, WegFehler
from .regeln import RegelFehler, gilt_am, normalisieren
from .simulation import Simulation

UHRZEIT = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
FARBE = re.compile(r"^(#[0-9a-fA-F]{6})?$")
RUECKWEG_MODI = ("leer", "beladen", "spaeter", "keiner")


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


class Wagentyp(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    plaetze: float = Field(gt=0, le=100)


class AufzugModell(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    art: str = "aufzug"
    plaetze: float = Field(ge=0, le=100)
    fahrzeit_etage: float = Field(ge=0, le=600)
    tuerzeit: float = Field(ge=0, le=600)
    raeumzeit: float = Field(ge=0, le=600)
    anfahrt: float = Field(ge=0, le=1800)
    transportarten: list[int] = []


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


class KnotenAenderung(BaseModel):
    x: float | None = None
    y: float | None = None
    art: str | None = None
    name: str | None = Field(default=None, max_length=100)
    aufzug_id: int | None = None
    kapazitaet: int | None = Field(default=None, ge=0, le=1000)


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


class Lieferung(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    lieferant: str = Field(default="", max_length=150)
    richtung: str = "versorgung"
    transportart_id: int
    start_id: int
    ziel_id: int
    uhrzeit: str
    spaetestens: str | None = None
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


def registrieren(app: FastAPI, db: Datenbank, fehler, ansehen, bearbeiten) -> None:
    def holen(tabelle: str, rid: int) -> dict:
        row = db.eins(f"SELECT * FROM {tabelle} WHERE id = ?", (rid,))
        if row is None:
            raise fehler(404, "nicht_gefunden")
        return row

    def farbe_pruefen(f: str) -> None:
        if not FARBE.match(f or ""):
            raise fehler(400, "farbe_ungueltig")

    # ---------------------------------------------------------------- Stammdaten
    def stammdaten() -> dict:
        auf = db.alle("SELECT * FROM aufzuege ORDER BY art, name")
        for a in auf:
            a["transportarten"] = json.loads(a["transportarten"])
        ta = db.alle("SELECT * FROM transportarten ORDER BY id")
        for t in ta:
            t["aufzug_exklusiv"], t["treppe"] = bool(t["aufzug_exklusiv"]), bool(t["treppe"])
        return {"transportarten": ta, "wagentypen": db.alle("SELECT * FROM wagentypen ORDER BY name"), "aufzuege": auf}

    @app.get("/api/stammdaten")
    def stammdaten_lesen(_: dict = Depends(ansehen)):
        return stammdaten()

    @app.post("/api/transportarten")
    def transportart_anlegen(d: Transportart, _: dict = Depends(bearbeiten)):
        farbe_pruefen(d.farbe)
        return {"id": db.ausfuehren(
            "INSERT INTO transportarten (name, farbe, geschwindigkeit, ladezeit, entladezeit, wagen_pro_fahrt, anzahl, aufzug_exklusiv, treppe) VALUES (?,?,?,?,?,?,?,?,?)",
            (d.name.strip(), d.farbe, d.geschwindigkeit, d.ladezeit, d.entladezeit, d.wagen_pro_fahrt, d.anzahl, int(d.aufzug_exklusiv), int(d.treppe)))}

    @app.put("/api/transportarten/{tid}")
    def transportart_aendern(tid: int, d: Transportart, _: dict = Depends(bearbeiten)):
        holen("transportarten", tid)
        farbe_pruefen(d.farbe)
        db.ausfuehren(
            "UPDATE transportarten SET name=?, farbe=?, geschwindigkeit=?, ladezeit=?, entladezeit=?, wagen_pro_fahrt=?, anzahl=?, aufzug_exklusiv=?, treppe=? WHERE id=?",
            (d.name.strip(), d.farbe, d.geschwindigkeit, d.ladezeit, d.entladezeit, d.wagen_pro_fahrt, d.anzahl, int(d.aufzug_exklusiv), int(d.treppe), tid))
        return {"ok": True}

    @app.delete("/api/transportarten/{tid}")
    def transportart_loeschen(tid: int, _: dict = Depends(bearbeiten)):
        if db.eins("SELECT 1 FROM lieferungen WHERE transportart_id = ?", (tid,)):
            raise fehler(409, "transportart_in_verwendung")
        db.ausfuehren("DELETE FROM transportarten WHERE id = ?", (tid,))
        return {"ok": True}

    @app.post("/api/wagentypen")
    def wagentyp_anlegen(d: Wagentyp, _: dict = Depends(bearbeiten)):
        return {"id": db.ausfuehren("INSERT INTO wagentypen (name, plaetze) VALUES (?, ?)", (d.name.strip(), d.plaetze))}

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

    def aufzug_pruefen(d: AufzugModell) -> None:
        if d.art not in ("aufzug", "treppe"):
            raise fehler(400, "art_ungueltig")

    @app.post("/api/aufzuege")
    def aufzug_anlegen(d: AufzugModell, _: dict = Depends(bearbeiten)):
        aufzug_pruefen(d)
        return {"id": db.ausfuehren(
            "INSERT INTO aufzuege (name, art, plaetze, fahrzeit_etage, tuerzeit, raeumzeit, anfahrt, transportarten) VALUES (?,?,?,?,?,?,?,?)",
            (d.name.strip(), d.art, d.plaetze, d.fahrzeit_etage, d.tuerzeit, d.raeumzeit, d.anfahrt, json.dumps(d.transportarten)))}

    @app.put("/api/aufzuege/{aid}")
    def aufzug_aendern(aid: int, d: AufzugModell, _: dict = Depends(bearbeiten)):
        holen("aufzuege", aid)
        aufzug_pruefen(d)
        db.ausfuehren(
            "UPDATE aufzuege SET name=?, art=?, plaetze=?, fahrzeit_etage=?, tuerzeit=?, raeumzeit=?, anfahrt=?, transportarten=? WHERE id=?",
            (d.name.strip(), d.art, d.plaetze, d.fahrzeit_etage, d.tuerzeit, d.raeumzeit, d.anfahrt, json.dumps(d.transportarten), aid))
        return {"ok": True}

    @app.delete("/api/aufzuege/{aid}")
    def aufzug_loeschen(aid: int, _: dict = Depends(bearbeiten)):
        db.ausfuehren("DELETE FROM aufzuege WHERE id = ?", (aid,))
        return {"ok": True}

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
    def flaeche_anlegen(d: Flaeche, _: dict = Depends(bearbeiten)):
        holen("stockwerke", d.stockwerk_id)
        flaeche_pruefen(d.art, d.punkte, d.farbe)
        punkte = [list(p) for p in d.punkte]
        parent = d.parent_id if d.parent_id is not None else (passender_bereich(d.stockwerk_id, punkte) if d.art == "raum" else None)
        fid = db.ausfuehren(
            "INSERT INTO flaechen (stockwerk_id, parent_id, art, name, nummer, farbe, punkte) VALUES (?,?,?,?,?,?,?)",
            (d.stockwerk_id, parent, d.art, d.name.strip(), d.nummer.strip(), d.farbe, json.dumps(punkte)))
        knoten_zuordnen(d.stockwerk_id)
        return {"id": fid, "parent_id": parent}

    @app.put("/api/flaechen/{fid}")
    def flaeche_aendern(fid: int, d: FlaecheAenderung, _: dict = Depends(bearbeiten)):
        f = holen("flaechen", fid)
        flaeche_pruefen(d.art, d.punkte, d.farbe)
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
    def flaeche_loeschen(fid: int, _: dict = Depends(bearbeiten)):
        f = holen("flaechen", fid)
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
    def punkte(_: dict = Depends(ansehen)):
        """Alle benannten Knoten (Start, Ziel, Aufzug …) für Auswahllisten."""
        return db.alle(
            """SELECT k.id, k.name, k.art, k.stockwerk_id, k.aufzug_id, s.name AS stockwerk, s.ebene,
                      g.id AS gebaeudeteil_id, g.name AS gebaeudeteil, g.kuerzel, f.name AS flaeche, f.nummer
                 FROM knoten k JOIN stockwerke s ON s.id = k.stockwerk_id
                 JOIN gebaeudeteile g ON g.id = s.gebaeudeteil_id
                 LEFT JOIN flaechen f ON f.id = k.flaeche_id
                WHERE k.art <> 'weg' OR k.name <> ''
                ORDER BY g.reihenfolge, g.name, s.ebene DESC, k.name"""
        )

    @app.post("/api/knoten")
    def knoten_anlegen(d: Knoten, _: dict = Depends(bearbeiten)):
        holen("stockwerke", d.stockwerk_id)
        knoten_pruefen(d.art, d.aufzug_id)
        kid = db.ausfuehren(
            "INSERT INTO knoten (stockwerk_id, x, y, art, name, aufzug_id, kapazitaet) VALUES (?,?,?,?,?,?,?)",
            (d.stockwerk_id, d.x, d.y, d.art, d.name.strip(), d.aufzug_id, d.kapazitaet))
        knoten_zuordnen(d.stockwerk_id)
        return {"id": kid}

    @app.put("/api/knoten/{kid}")
    def knoten_aendern(kid: int, d: KnotenAenderung, _: dict = Depends(bearbeiten)):
        k = holen("knoten", kid)
        felder = d.model_dump(exclude_unset=True)
        knoten_pruefen(felder.get("art"), felder.get("aufzug_id"))
        if felder.get("kapazitaet") == 0:
            felder["kapazitaet"] = None
        if "name" in felder:
            felder["name"] = felder["name"].strip()
        if felder:
            sets = ", ".join(f"{f} = ?" for f in felder)
            db.ausfuehren(f"UPDATE knoten SET {sets} WHERE id = ?", (*felder.values(), kid))
        if "x" in felder or "y" in felder:
            knoten_zuordnen(k["stockwerk_id"])
        return {"ok": True}

    @app.delete("/api/knoten/{kid}")
    def knoten_loeschen(kid: int, _: dict = Depends(bearbeiten)):
        holen("knoten", kid)
        if db.eins("SELECT 1 FROM lieferungen WHERE start_id = ? OR ziel_id = ?", (kid, kid)) or any(
            kid in json.loads(l["via"]) or json.loads(l["rueckweg"]).get("ziel_id") == kid for l in db.alle("SELECT via, rueckweg FROM lieferungen")
        ):
            raise fehler(409, "knoten_in_verwendung")
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
    def kante_anlegen(d: Kante, _: dict = Depends(bearbeiten)):
        von, nach = holen("knoten", d.von), holen("knoten", d.nach)
        kante_pruefen(von, nach, d.laenge_m, d.gesperrt)
        vorhanden = db.eins("SELECT id FROM kanten WHERE (von = ? AND nach = ?) OR (von = ? AND nach = ?)", (d.von, d.nach, d.nach, d.von))
        if vorhanden:
            return {"id": vorhanden["id"]}
        return {"id": db.ausfuehren(
            "INSERT INTO kanten (von, nach, laenge_m, kapazitaet, gesperrt, name) VALUES (?,?,?,?,?,?)",
            (d.von, d.nach, d.laenge_m, d.kapazitaet, json.dumps(sorted(set(d.gesperrt))), d.name.strip()))}

    @app.put("/api/kanten/{kid}")
    def kante_aendern(kid: int, d: KanteAenderung, _: dict = Depends(bearbeiten)):
        k = holen("kanten", kid)
        felder = d.model_dump(exclude_unset=True)
        von, nach = holen("knoten", k["von"]), holen("knoten", k["nach"])
        laenge = felder.get("laenge_m", k["laenge_m"]) or None
        kante_pruefen(von, nach, laenge, felder.get("gesperrt"))
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
    def kante_loeschen(kid: int, _: dict = Depends(bearbeiten)):
        db.ausfuehren("DELETE FROM kanten WHERE id = ?", (kid,))
        return {"ok": True}

    @app.post("/api/kanten/{kid}/teilen")
    def kante_teilen(kid: int, d: Teilen, _: dict = Depends(bearbeiten)):
        """Setzt einen neuen Wegknoten auf die Kante (nächster Punkt zu x/y) und teilt sie."""
        k = holen("kanten", kid)
        a, b = holen("knoten", k["von"]), holen("knoten", k["nach"])
        if a["stockwerk_id"] != b["stockwerk_id"]:
            raise fehler(400, "kante_ungueltig")
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

    def lieferung_pruefen(d: Lieferung) -> dict:
        if d.richtung not in ("versorgung", "entsorgung"):
            raise fehler(400, "richtung_ungueltig")
        for z in (d.uhrzeit, d.spaetestens, d.rueckweg.uhrzeit):
            if z and not UHRZEIT.match(z):
                raise fehler(400, "uhrzeit_ungueltig")
        holen("transportarten", d.transportart_id)
        for kid in [d.start_id, d.ziel_id, *d.via, *([d.rueckweg.ziel_id] if d.rueckweg.ziel_id else [])]:
            holen("knoten", kid)
        if d.start_id == d.ziel_id:
            raise fehler(400, "start_gleich_ziel")
        wt = {w["id"] for w in db.alle("SELECT id FROM wagentypen")}
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
            "uhrzeit": d.uhrzeit, "spaetestens": d.spaetestens or None,
            "ladung": json.dumps([p.model_dump() for p in d.ladung if p.anzahl > 0]),
            "via": json.dumps(d.via), "regel": json.dumps(regel), "rueckweg": json.dumps(d.rueckweg.model_dump()),
            "aktiv": int(d.aktiv), "notiz": d.notiz,
        }

    @app.get("/api/lieferungen")
    def lieferungen(_: dict = Depends(ansehen)):
        return [lieferung_lesen(r) for r in db.alle("SELECT * FROM lieferungen ORDER BY uhrzeit, name")]

    @app.post("/api/lieferungen")
    def lieferung_anlegen(d: Lieferung, _: dict = Depends(bearbeiten)):
        werte = lieferung_pruefen(d)
        sp = ", ".join(werte)
        return {"id": db.ausfuehren(f"INSERT INTO lieferungen ({sp}) VALUES ({', '.join('?' * len(werte))})", tuple(werte.values()))}

    @app.put("/api/lieferungen/{lid}")
    def lieferung_aendern(lid: int, d: Lieferung, _: dict = Depends(bearbeiten)):
        holen("lieferungen", lid)
        werte = lieferung_pruefen(d)
        sets = ", ".join(f"{k} = ?" for k in werte)
        db.ausfuehren(f"UPDATE lieferungen SET {sets} WHERE id = ?", (*werte.values(), lid))
        return {"ok": True}

    @app.delete("/api/lieferungen/{lid}")
    def lieferung_loeschen(lid: int, _: dict = Depends(bearbeiten)):
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
        bl = db.einstellung("bundesland", "NW")
        sonder = {s["datum"] for s in db.alle("SELECT datum FROM sondertage")}
        cache: dict[int, set] = {}

        def pruefen(tag: date) -> tuple[bool, str | None]:
            if tag.year not in cache:
                cache[tag.year] = {d.isoformat(): k for d, k in feiertage(tag.year, bl)}
            iso = tag.isoformat()
            if iso in cache[tag.year]:
                return True, cache[tag.year][iso]
            if iso in sonder:
                return True, db.eins("SELECT name FROM sondertage WHERE datum = ?", (iso,))["name"]
            return False, None

        return pruefen

    @app.get("/api/simulation")
    def simulation(datum: str | None = None, _: dict = Depends(ansehen)):
        try:
            tag = date.fromisoformat(datum) if datum else date.today()
        except ValueError:
            raise fehler(400, "datum_ungueltig")
        feiertag, feiertag_name = ist_feiertag_fn()(tag)
        alle = [lieferung_lesen(r) for r in db.alle("SELECT * FROM lieferungen WHERE aktiv = 1 ORDER BY uhrzeit, id")]
        heute = [l for l in alle if gilt_am(l["regel"], tag, feiertag)]
        sd = stammdaten()
        sim = Simulation(Netz(db), {t["id"]: t for t in sd["transportarten"]}, {w["id"]: w for w in sd["wagentypen"]})
        for l in heute:
            sim.lieferung_einplanen(l)
        ergebnis = sim.laufen()
        ergebnis.update({"datum": tag.isoformat(), "feiertag": feiertag_name, "wochentag": tag.isoweekday(), "lieferungen": [l["id"] for l in heute]})
        return ergebnis

    @app.get("/api/kalender")
    def kalender(von: str, tage: int = 14, _: dict = Depends(ansehen)):
        """Welche Lieferungen an den nächsten Tagen stattfinden (für die Vorschau der Regeln)."""
        try:
            start = date.fromisoformat(von)
        except ValueError:
            raise fehler(400, "datum_ungueltig")
        tage = max(1, min(tage, 62))
        pruefen = ist_feiertag_fn()
        alle = [lieferung_lesen(r) for r in db.alle("SELECT id, regel, aktiv, ladung, via, rueckweg FROM lieferungen")]
        ergebnis = []
        for i in range(tage):
            tag = date.fromordinal(start.toordinal() + i)
            ft, name = pruefen(tag)
            ergebnis.append({
                "datum": tag.isoformat(), "feiertag": name,
                "lieferungen": [l["id"] for l in alle if l["aktiv"] and gilt_am(l["regel"], tag, ft)],
            })
        return ergebnis

