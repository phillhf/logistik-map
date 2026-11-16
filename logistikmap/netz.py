"""Wegenetz und Wegsuche.

Knoten liegen auf einem Stockwerk (Koordinaten in PDF-Punkten). Kanten verbinden zwei Knoten:
auf demselben Stockwerk ergibt sich die Länge aus dem Maßstab, zwischen Stockwerken bzw.
Gebäudeteilen (Übergang) muss sie in Metern angegeben sein. Knoten mit derselben aufzug_id
sind über den Aufzug bzw. die Treppe verbunden.

Die Wegsuche nimmt den schnellsten Weg für eine Transportart (Dijkstra) und beachtet Sperren,
erlaubte Transportarten der Aufzüge und ob die Transportart Treppen nutzen kann.
"""

from __future__ import annotations

import heapq
import json
import math
from dataclasses import dataclass, field

from .db import Datenbank

KNOTEN_ARTEN = ("weg", "start", "ziel", "punkt", "aufzug", "uebergang")
BENANNTE_ARTEN = ("start", "ziel", "punkt", "aufzug", "uebergang")


class WegFehler(Exception):
    def __init__(self, code: str, **extra):
        super().__init__(code)
        self.code = code
        self.extra = extra


@dataclass
class Abschnitt:
    """Teil eines Wegs: Fußweg über eine Kante oder Fahrt mit Aufzug/Treppe."""

    typ: str  # "weg" | "aufzug"
    von: int
    nach: int
    dauer: float  # reine Fahr-/Gehzeit in Sekunden, ohne Warten
    laenge_m: float = 0.0
    kante_id: int | None = None
    aufzug_id: int | None = None
    etagen: int = 0

    def als_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if v is not None}


@dataclass
class Weg:
    abschnitte: list[Abschnitt] = field(default_factory=list)

    @property
    def dauer(self) -> float:
        return sum(a.dauer for a in self.abschnitte)

    @property
    def laenge_m(self) -> float:
        return sum(a.laenge_m for a in self.abschnitte)

    @property
    def knoten(self) -> list[int]:
        if not self.abschnitte:
            return []
        return [self.abschnitte[0].von] + [a.nach for a in self.abschnitte]


def aufzug_fahrzeit(aufzug: dict, etagen: int, exklusiv: bool, mit_anfahrt: bool = True) -> float:
    """Fahrzeit einer Aufzugfahrt. mit_anfahrt=False, wenn die Kabine gerade schon auf dem Stockwerk steht."""
    if aufzug["art"] == "treppe":
        return etagen * aufzug["fahrzeit_etage"]
    zeit = (aufzug["anfahrt"] if mit_anfahrt else 0) + 2 * aufzug["tuerzeit"] + etagen * aufzug["fahrzeit_etage"]
    if exklusiv:
        zeit += aufzug["raeumzeit"]
    return zeit


class Netz:
    """Momentaufnahme des Wegenetzes aus der Datenbank."""

    def __init__(self, db: Datenbank):
        self.stockwerke = {s["id"]: s for s in db.alle("SELECT id, name, ebene, gebaeudeteil_id, meter_pro_punkt FROM stockwerke")}
        self.knoten = {k["id"]: k for k in db.alle("SELECT * FROM knoten")}
        self.aufzuege = {a["id"]: a for a in db.alle("SELECT * FROM aufzuege")}
        for a in self.aufzuege.values():
            a["transportarten"] = json.loads(a["transportarten"])
        self.kanten = {k["id"]: k for k in db.alle("SELECT * FROM kanten")}
        self.nachbarn: dict[int, list[tuple[int, dict]]] = {kid: [] for kid in self.knoten}
        for k in self.kanten.values():
            k["gesperrt"] = json.loads(k["gesperrt"])
            k["laenge"] = self._laenge(k)
            if k["von"] in self.nachbarn and k["nach"] in self.nachbarn:
                self.nachbarn[k["von"]].append((k["nach"], k))
                self.nachbarn[k["nach"]].append((k["von"], k))
        self.aufzug_halte: dict[int, list[int]] = {}
        for k in self.knoten.values():
            if k["aufzug_id"] in self.aufzuege:
                self.aufzug_halte.setdefault(k["aufzug_id"], []).append(k["id"])

    def _laenge(self, k: dict) -> float | None:
        if k["laenge_m"] is not None:
            return k["laenge_m"]
        a, b = self.knoten.get(k["von"]), self.knoten.get(k["nach"])
        if a is None or b is None or a["stockwerk_id"] != b["stockwerk_id"]:
            return None
        mpp = self.stockwerke[a["stockwerk_id"]]["meter_pro_punkt"]
        if not mpp:
            return None
        return math.hypot(a["x"] - b["x"], a["y"] - b["y"]) * mpp

    def ebene(self, knoten_id: int) -> int:
        return self.stockwerke[self.knoten[knoten_id]["stockwerk_id"]]["ebene"]

    def weg(self, start: int, ziel: int, transportart: dict, via: list[int] | None = None) -> Weg:
        punkte = [start, *(via or []), ziel]
        for p in punkte:
            if p not in self.knoten:
                raise WegFehler("knoten_unbekannt", knoten=p)
        gesamt = Weg()
        for a, b in zip(punkte, punkte[1:]):
            gesamt.abschnitte.extend(self._dijkstra(a, b, transportart).abschnitte)
        return gesamt

    def _dijkstra(self, start: int, ziel: int, ta: dict) -> Weg:
        if start == ziel:
            return Weg()
        tempo = max(ta["geschwindigkeit"], 0.05)
        exklusiv = bool(ta["aufzug_exklusiv"])
        dist = {start: 0.0}
        vorher: dict[int, tuple[int, Abschnitt]] = {}
        heap = [(0.0, start)]
        fehlender_massstab: set[int] = set()
        while heap:
            d, k = heapq.heappop(heap)
            if k == ziel:
                break
            if d > dist.get(k, math.inf):
                continue
            for n, kante in self.nachbarn[k]:
                if ta["id"] in kante["gesperrt"]:
                    continue
                if kante["laenge"] is None:
                    fehlender_massstab.add(self.knoten[k]["stockwerk_id"])
                    continue
                schritt = Abschnitt("weg", k, n, kante["laenge"] / tempo, kante["laenge"], kante_id=kante["id"])
                self._entspannen(heap, dist, vorher, d, n, schritt)
            aid = self.knoten[k]["aufzug_id"]
            if aid in self.aufzuege:
                auf = self.aufzuege[aid]
                if auf["transportarten"] and ta["id"] not in auf["transportarten"]:
                    continue
                if auf["art"] == "treppe" and not ta["treppe"]:
                    continue
                for n in self.aufzug_halte[aid]:
                    if n == k:
                        continue
                    etagen = abs(self.ebene(n) - self.ebene(k))
                    schritt = Abschnitt("aufzug", k, n, aufzug_fahrzeit(auf, etagen, exklusiv), aufzug_id=aid, etagen=etagen)
                    self._entspannen(heap, dist, vorher, d, n, schritt)
        if ziel not in dist:
            if fehlender_massstab:
                namen = ", ".join(sorted(self.stockwerke[s]["name"] for s in fehlender_massstab))
                raise WegFehler("massstab_fehlt", stockwerke=namen)
            raise WegFehler("kein_weg", start=self.knoten[start]["name"], ziel=self.knoten[ziel]["name"])
        abschnitte = []
        k = ziel
        while k != start:
            k_vor, a = vorher[k]
            abschnitte.append(a)
            k = k_vor
        return Weg(list(reversed(abschnitte)))

    @staticmethod
    def _entspannen(heap, dist, vorher, d, n, schritt: Abschnitt) -> None:
        nd = d + schritt.dauer
        if nd < dist.get(n, math.inf):
            dist[n] = nd
            vorher[n] = (schritt.von, schritt)
            heapq.heappush(heap, (nd, n))

    # ---------------------------------------------------------------- Prüfen (Erste Schritte)
    def erreichbar(self, start: int, transportart: dict | None = None) -> tuple[set[int], set[int], bool]:
        """Knoten, die von start aus erreichbar sind.

        Ohne Transportart zählt jede Verbindung. Mit Transportart gelten deren Sperren; zurück
        kommen dann auch die Aufzüge/Treppen, an denen sie nicht weiterkam, und ob eine Kante
        für sie gesperrt war.
        """
        gesehen = {start}
        offen = [start]
        aufzug_gesperrt: set[int] = set()
        kante_gesperrt = False
        while offen:
            k = offen.pop()
            for n, kante in self.nachbarn.get(k, []):
                if transportart and transportart["id"] in kante["gesperrt"]:
                    kante_gesperrt = True
                    continue
                if n not in gesehen:
                    gesehen.add(n)
                    offen.append(n)
            aid = self.knoten[k]["aufzug_id"]
            if aid in self.aufzuege:
                auf = self.aufzuege[aid]
                if transportart and (
                    (auf["transportarten"] and transportart["id"] not in auf["transportarten"])
                    or (auf["art"] == "treppe" and not transportart["treppe"])
                ):
                    if len(self.aufzug_halte.get(aid, [])) > 1:
                        aufzug_gesperrt.add(aid)
                    continue
                for n in self.aufzug_halte[aid]:
                    if n not in gesehen:
                        gesehen.add(n)
                        offen.append(n)
        return gesehen, aufzug_gesperrt, kante_gesperrt

    def stockwerk_name(self, sid: int, teile: dict[int, str] | None = None) -> str:
        s = self.stockwerke[sid]
        teil = (teile or {}).get(s["gebaeudeteil_id"])
        return f"{s['name']} ({teil})" if teil else s["name"]

    def weg_diagnose(self, start: int, ziel: int, transportart: dict, teile: dict[int, str] | None = None) -> dict:
        """Erklärt, warum es keinen Weg von start nach ziel gibt (für die Seite „Erste Schritte“)."""
        if start not in self.knoten or ziel not in self.knoten:
            return {"code": "punkt_fehlt"}
        frei, _, _ = self.erreichbar(start)
        if ziel not in frei:
            sw_start = self.knoten[start]["stockwerk_id"]
            sw_ziel = self.knoten[ziel]["stockwerk_id"]
            if sw_start == sw_ziel and not any(self.knoten[k]["stockwerk_id"] != sw_start for k in frei):
                return {"code": "weg_unterbrochen", "stockwerk": self.stockwerk_name(sw_start, teile), "stockwerk_id": sw_start}
            erreicht = sorted({self.knoten[k]["stockwerk_id"] for k in frei}, key=lambda s: (self.stockwerke[s]["gebaeudeteil_id"], -self.stockwerke[s]["ebene"]))
            return {
                "code": "keine_verbindung",
                "erreichbar": ", ".join(self.stockwerk_name(s, teile) for s in erreicht),
                "ziel_stockwerk": self.stockwerk_name(sw_ziel, teile),
                "stockwerk_id": sw_ziel,
            }
        _, aufzuege, kanten = self.erreichbar(start, transportart)
        namen = sorted(self.aufzuege[a]["name"] for a in aufzuege)
        if namen:
            return {"code": "aufzug_nicht_erlaubt", "aufzuege": ", ".join(namen)}
        if kanten:
            return {"code": "weg_gesperrt", "stockwerk_id": self.knoten[start]["stockwerk_id"]}
        return {"code": "kein_weg"}
