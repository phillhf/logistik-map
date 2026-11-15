"""Ablauf eines Tages: Lieferungen → Fahrten → Belegung von Fahrzeugen, Aufzügen und Engstellen.

Grob gerechnet, aber mit echten Wartezeiten (ereignisgesteuerte Simulation):

* Eine Lieferung mit N Wagen ergibt ceil(N / wagen_pro_fahrt) Fahrten.
* Jede Fahrt braucht ein Fahrzeug bzw. eine Person der Transportart (anzahl 0 = unbegrenzt).
  Sie belegt es bis zur Rückkehr.
* Ablauf einer Fahrt: Laden am Start → Weg (Flure, Aufzüge, Treppen) → Entladen am Ziel →
  Rückweg je nach Lieferung (leer zurück, beladen zurück, kein Rückweg).
* Aufzüge sind eine Kabine: Wer wartet, steigt in Ankunftsreihenfolge ein. Fahrten mit
  gleichem Start- und Zielstockwerk fahren gemeinsam, solange die Plätze reichen.
  FTS (aufzug_exklusiv) fahren allein und brauchen zusätzlich die Räumzeit.
* Kanten und Knoten mit Kapazität (Engstellen, Rampen) lassen nur so viele Fahrten gleichzeitig zu.
  Knoten werden während des Ladens bzw. Entladens belegt, Kanten während des Durchfahrens.

Alle Zeiten in Sekunden seit Mitternacht des simulierten Tages.
"""

from __future__ import annotations

import heapq
import math
from collections import deque
from dataclasses import dataclass, field

from .netz import Netz, Weg, WegFehler, aufzug_fahrzeit

RASTER = 300  # Auslastung in 5-Minuten-Schritten
MAX_ZEIT = 2 * 86400


def zeit_in_sekunden(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 3600 + int(m) * 60


# --------------------------------------------------------------------------- Simulationskern
class _Uhr:
    def __init__(self):
        self.jetzt = 0.0
        self._heap: list = []
        self._nr = 0

    def plane(self, zeit: float, fn, *args) -> None:
        self._nr += 1
        heapq.heappush(self._heap, (zeit, self._nr, fn, args))

    def laufen(self) -> None:
        while self._heap:
            zeit, _, fn, args = heapq.heappop(self._heap)
            if zeit > MAX_ZEIT:
                break
            self.jetzt = zeit
            fn(*args)


class _Prozess:
    def __init__(self, uhr: _Uhr, gen):
        self.uhr = uhr
        self.gen = gen

    def weiter(self, wert=None) -> None:
        try:
            befehl = self.gen.send(wert)
        except StopIteration:
            return
        art = befehl[0]
        if art == "warte":
            self.uhr.plane(self.uhr.jetzt + befehl[1], self.weiter)
        elif art == "belege":
            befehl[1].anfordern(self, befehl[2])
        elif art == "aufzug":
            befehl[1].anfordern(self, *befehl[2:])
        else:  # pragma: no cover
            raise ValueError(art)


@dataclass
class Ressource:
    """Kapazität mit Warteschlange (Fahrzeuge, Engstellen, Rampen)."""

    uhr: _Uhr
    typ: str
    rid: int
    name: str
    kapazitaet: int | None  # None = unbegrenzt
    stockwerk_id: int | None = None
    belegt: int = 0
    schlange: deque = field(default_factory=deque)
    verlauf: list = field(default_factory=list)  # (zeit, belegt, wartend)
    wartezeiten: list = field(default_factory=list)

    def _passt(self, menge: int) -> bool:
        return self.kapazitaet is None or self.belegt == 0 or self.belegt + menge <= self.kapazitaet

    def _merken(self) -> None:
        self.verlauf.append((self.uhr.jetzt, self.belegt, len(self.schlange)))

    def anfordern(self, prozess: _Prozess, menge: int) -> None:
        if not self.schlange and self._passt(menge):
            self.belegt += menge
            self.wartezeiten.append(0.0)
            self._merken()
            self.uhr.plane(self.uhr.jetzt, prozess.weiter, 0.0)
        else:
            self.schlange.append((prozess, menge, self.uhr.jetzt))
            self._merken()

    def freigeben(self, menge: int) -> None:
        self.belegt -= menge
        while self.schlange and self._passt(self.schlange[0][1]):
            prozess, m, seit = self.schlange.popleft()
            self.belegt += m
            warte = self.uhr.jetzt - seit
            self.wartezeiten.append(warte)
            self.uhr.plane(self.uhr.jetzt, prozess.weiter, warte)
        self._merken()


@dataclass
class Aufzug:
    """Eine Kabine, fährt Gruppen von Fahrten mit gleichem Start- und Zielstockwerk."""

    uhr: _Uhr
    daten: dict
    fahrten: list = field(default_factory=list)  # (start, ende, plaetze, anzahl, exklusiv)
    schlange: list = field(default_factory=list)
    verlauf: list = field(default_factory=list)  # (zeit, belegt 0/1, wartend)
    wartezeiten: list = field(default_factory=list)
    unterwegs: bool = False
    abfahrt_geplant: bool = False
    zu_gross: int = 0

    @property
    def plaetze(self) -> float | None:
        return self.daten["plaetze"] or None

    def anfordern(self, prozess, von_ebene: int, nach_ebene: int, plaetze: float, exklusiv: bool) -> None:
        self.schlange.append({"p": prozess, "von": von_ebene, "nach": nach_ebene, "plaetze": plaetze, "exklusiv": exklusiv, "seit": self.uhr.jetzt})
        self.verlauf.append((self.uhr.jetzt, int(self.unterwegs), len(self.schlange)))
        if not self.unterwegs and not self.abfahrt_geplant:
            # erst am Ende dieses Zeitpunkts abfahren: Wagen, die gleichzeitig ankommen, fahren mit
            self.abfahrt_geplant = True
            self.uhr.plane(self.uhr.jetzt, self._abfahren)

    def _abfahren(self) -> None:
        self.abfahrt_geplant = False
        if self.unterwegs or not self.schlange:
            return
        erste = self.schlange.pop(0)
        gruppe = [erste]
        frei = math.inf if self.plaetze is None else self.plaetze - erste["plaetze"]
        if self.plaetze is not None and erste["plaetze"] > self.plaetze:
            self.zu_gross += 1
        if not erste["exklusiv"]:
            for anf in list(self.schlange):
                if not anf["exklusiv"] and anf["von"] == erste["von"] and anf["nach"] == erste["nach"] and anf["plaetze"] <= frei:
                    gruppe.append(anf)
                    frei -= anf["plaetze"]
                    self.schlange.remove(anf)
        etagen = abs(erste["nach"] - erste["von"])
        dauer = aufzug_fahrzeit(self.daten, etagen, erste["exklusiv"])
        start = self.uhr.jetzt
        self.unterwegs = True
        self.fahrten.append((start, start + dauer, sum(a["plaetze"] for a in gruppe), len(gruppe), erste["exklusiv"]))
        self.verlauf.append((start, 1, len(self.schlange)))
        for anf in gruppe:
            self.wartezeiten.append(start - anf["seit"])
            self.uhr.plane(start + dauer, anf["p"].weiter, (start - anf["seit"], start, start + dauer))
        self.uhr.plane(start + dauer, self._angekommen)

    def _angekommen(self) -> None:
        self.unterwegs = False
        self.verlauf.append((self.uhr.jetzt, 0, len(self.schlange)))
        if self.schlange:
            self._abfahren()


# --------------------------------------------------------------------------- Fahrten
@dataclass
class Fahrt:
    id: int
    lieferung: dict
    nr: int
    von_n: int
    geplant: float
    wagen: list  # [{wagentyp_id, name, plaetze}]
    start_id: int
    ziel_id: int
    rueck: str  # leer | beladen | keiner
    rueck_ziel_id: int | None
    art: str = "hin"  # hin | spaeter (eigene Rückfahrt zu fester Uhrzeit)
    start: float | None = None
    ankunft: float | None = None
    fertig: float | None = None
    ende: float | None = None
    warte: dict = field(default_factory=lambda: {"fahrzeug": 0.0, "aufzug": 0.0, "engstelle": 0.0})
    abschnitte: list = field(default_factory=list)

    @property
    def plaetze(self) -> float:
        return sum(w["plaetze"] for w in self.wagen)


class Simulation:
    def __init__(self, netz: Netz, transportarten: dict[int, dict], wagentypen: dict[int, dict]):
        self.netz = netz
        self.transportarten = transportarten
        self.wagentypen = wagentypen
        self.uhr = _Uhr()
        self.flotten: dict[int, Ressource] = {}
        self.aufzuege: dict[int, Aufzug] = {}
        self.kanten: dict[int, Ressource] = {}
        self.knoten: dict[int, Ressource] = {}
        self.fahrten: list[Fahrt] = []
        self.fehler: list[dict] = []
        self._wege: dict = {}

    # -- Ressourcen -------------------------------------------------------------
    def _flotte(self, ta: dict) -> Ressource | None:
        if not ta["anzahl"]:
            return None
        if ta["id"] not in self.flotten:
            self.flotten[ta["id"]] = Ressource(self.uhr, "fahrzeuge", ta["id"], ta["name"], ta["anzahl"])
        return self.flotten[ta["id"]]

    def _aufzug(self, aid: int) -> Aufzug:
        if aid not in self.aufzuege:
            self.aufzuege[aid] = Aufzug(self.uhr, self.netz.aufzuege[aid])
        return self.aufzuege[aid]

    def _kante(self, kid: int) -> Ressource | None:
        k = self.netz.kanten[kid]
        if not k["kapazitaet"]:
            return None
        if kid not in self.kanten:
            name = k["name"] or f"{self.netz.knoten[k['von']]['name'] or '·'} – {self.netz.knoten[k['nach']]['name'] or '·'}"
            sw = self.netz.knoten[k["von"]]["stockwerk_id"]
            self.kanten[kid] = Ressource(self.uhr, "kante", kid, name, k["kapazitaet"], sw)
        return self.kanten[kid]

    def _knoten(self, nid: int) -> Ressource | None:
        n = self.netz.knoten[nid]
        if not n["kapazitaet"]:
            return None
        if nid not in self.knoten:
            self.knoten[nid] = Ressource(self.uhr, "knoten", nid, n["name"] or f"#{nid}", n["kapazitaet"], n["stockwerk_id"])
        return self.knoten[nid]

    def _weg(self, start: int, ziel: int, ta: dict, via: list[int]) -> Weg:
        schluessel = (start, ziel, ta["id"], tuple(via))
        if schluessel not in self._wege:
            self._wege[schluessel] = self.netz.weg(start, ziel, ta, via)
        return self._wege[schluessel]

    # -- Fahrten anlegen ----------------------------------------------------------
    def lieferung_einplanen(self, l: dict) -> None:
        ta = self.transportarten.get(l["transportart_id"])
        if ta is None:
            self.fehler.append({"lieferung_id": l["id"], "name": l["name"], "code": "transportart_fehlt"})
            return
        wagen = []
        for pos in l["ladung"]:
            wt = self.wagentypen.get(pos.get("wagentyp_id"))
            if wt is None:
                continue
            wagen += [{"wagentyp_id": wt["id"], "name": wt["name"], "plaetze": wt["plaetze"]}] * max(0, int(pos.get("anzahl", 0)))
        if not wagen:
            wagen = [{"wagentyp_id": None, "name": "", "plaetze": 1.0}]
        rueck = l["rueckweg"] or {}
        modus = rueck.get("modus", "leer")
        rueck_ziel = rueck.get("ziel_id") or l["start_id"]
        try:
            self._weg(l["start_id"], l["ziel_id"], ta, l["via"])
            if modus in ("leer", "beladen"):
                self._weg(l["ziel_id"], rueck_ziel, ta, [])
            if modus == "spaeter":
                self._weg(l["ziel_id"], rueck_ziel, ta, [])
        except WegFehler as e:
            self.fehler.append({"lieferung_id": l["id"], "name": l["name"], "code": e.code, **e.extra})
            return
        pro = max(1, ta["wagen_pro_fahrt"])
        gruppen = [wagen[i : i + pro] for i in range(0, len(wagen), pro)]
        for nr, gruppe in enumerate(gruppen, start=1):
            f = Fahrt(
                id=len(self.fahrten) + 1,
                lieferung=l,
                nr=nr,
                von_n=len(gruppen),
                geplant=zeit_in_sekunden(l["uhrzeit"]),
                wagen=gruppe,
                start_id=l["start_id"],
                ziel_id=l["ziel_id"],
                rueck="leer" if modus == "spaeter" else modus,
                rueck_ziel_id=rueck_ziel,
            )
            self.fahrten.append(f)
            self.uhr.plane(f.geplant, _Prozess(self.uhr, self._ablauf(f, ta)).weiter)
            if modus == "spaeter" and rueck.get("uhrzeit"):
                r = Fahrt(
                    id=len(self.fahrten) + 1,
                    lieferung=l,
                    nr=nr,
                    von_n=len(gruppen),
                    geplant=zeit_in_sekunden(rueck["uhrzeit"]),
                    wagen=gruppe,
                    start_id=l["ziel_id"],
                    ziel_id=rueck_ziel,
                    rueck="keiner",
                    rueck_ziel_id=None,
                    art="spaeter",
                )
                self.fahrten.append(r)
                self.uhr.plane(r.geplant, _Prozess(self.uhr, self._ablauf(r, ta)).weiter)

    # -- Ablauf einer Fahrt (Generator) ---------------------------------------------
    def _ablauf(self, f: Fahrt, ta: dict):
        uhr = self.uhr
        flotte = self._flotte(ta)
        if flotte:
            seit = uhr.jetzt
            yield ("belege", flotte, 1)
            f.warte["fahrzeug"] += uhr.jetzt - seit
            if uhr.jetzt > seit:
                self._notiz(f, "warten", f.start_id, seit, uhr.jetzt, grund="fahrzeug")
        f.start = uhr.jetzt
        yield from self._an_knoten(f, f.start_id, ta["ladezeit"], "laden")
        via = f.lieferung["via"] if f.art == "hin" else []
        yield from self._fahren(f, self._weg(f.start_id, f.ziel_id, ta, via), ta, rueck=False)
        f.ankunft = uhr.jetzt
        yield from self._an_knoten(f, f.ziel_id, ta["entladezeit"], "entladen")
        f.fertig = uhr.jetzt
        if f.rueck in ("leer", "beladen"):
            yield from self._fahren(f, self._weg(f.ziel_id, f.rueck_ziel_id, ta, []), ta, rueck=True)
            if f.rueck == "beladen":
                yield from self._an_knoten(f, f.rueck_ziel_id, ta["entladezeit"], "entladen", rueck=True)
        f.ende = uhr.jetzt
        if flotte:
            flotte.freigeben(1)

    def _an_knoten(self, f: Fahrt, nid: int, dauer: float, art: str, rueck: bool = False):
        res = self._knoten(nid)
        if res:
            seit = self.uhr.jetzt
            yield ("belege", res, 1)
            if self.uhr.jetzt > seit:
                f.warte["engstelle"] += self.uhr.jetzt - seit
                self._notiz(f, "warten", nid, seit, self.uhr.jetzt, grund="engstelle", rueck=rueck)
        t0 = self.uhr.jetzt
        yield ("warte", dauer)
        self._notiz(f, art, nid, t0, self.uhr.jetzt, rueck=rueck)
        if res:
            res.freigeben(1)

    def _fahren(self, f: Fahrt, weg: Weg, ta: dict, rueck: bool):
        netz = self.netz
        for a in weg.abschnitte:
            if a.typ == "weg":
                res = self._kante(a.kante_id)
                if res:
                    seit = self.uhr.jetzt
                    yield ("belege", res, 1)
                    if self.uhr.jetzt > seit:
                        f.warte["engstelle"] += self.uhr.jetzt - seit
                        self._notiz(f, "warten", a.von, seit, self.uhr.jetzt, grund="engstelle", rueck=rueck)
                t0 = self.uhr.jetzt
                yield ("warte", a.dauer)
                self._weg_notiz(f, a.von, a.nach, t0, self.uhr.jetzt, rueck)
                if res:
                    res.freigeben(1)
            else:
                auf = netz.aufzuege[a.aufzug_id]
                t0 = self.uhr.jetzt
                if auf["art"] == "treppe":
                    yield ("warte", a.dauer)
                    einstieg, ende = t0, self.uhr.jetzt
                else:
                    warte, einstieg, ende = yield ("aufzug", self._aufzug(a.aufzug_id), netz.ebene(a.von), netz.ebene(a.nach), f.plaetze, bool(ta["aufzug_exklusiv"]))
                    f.warte["aufzug"] += warte
                von, nach = netz.knoten[a.von], netz.knoten[a.nach]
                f.abschnitte.append(
                    {
                        "typ": "aufzug",
                        "aufzug_id": a.aufzug_id,
                        "von": a.von,
                        "nach": a.nach,
                        "von_stockwerk": von["stockwerk_id"],
                        "nach_stockwerk": nach["stockwerk_id"],
                        "x0": von["x"], "y0": von["y"], "x1": nach["x"], "y1": nach["y"],
                        "t0": t0, "t_einstieg": einstieg, "t1": ende, "rueck": rueck,
                    }
                )

    def _weg_notiz(self, f: Fahrt, von: int, nach: int, t0: float, t1: float, rueck: bool) -> None:
        a, b = self.netz.knoten[von], self.netz.knoten[nach]
        if a["stockwerk_id"] == b["stockwerk_id"]:
            f.abschnitte.append({"typ": "weg", "stockwerk_id": a["stockwerk_id"], "von": von, "nach": nach,
                                 "x0": a["x"], "y0": a["y"], "x1": b["x"], "y1": b["y"], "t0": t0, "t1": t1, "rueck": rueck})
        else:  # Übergang zwischen Gebäudeteilen
            f.abschnitte.append({"typ": "uebergang", "von": von, "nach": nach, "von_stockwerk": a["stockwerk_id"], "nach_stockwerk": b["stockwerk_id"],
                                 "x0": a["x"], "y0": a["y"], "x1": b["x"], "y1": b["y"], "t0": t0, "t1": t1, "rueck": rueck})

    def _notiz(self, f: Fahrt, typ: str, nid: int, t0: float, t1: float, grund: str | None = None, rueck: bool = False) -> None:
        n = self.netz.knoten[nid]
        eintrag = {"typ": typ, "knoten": nid, "stockwerk_id": n["stockwerk_id"], "x": n["x"], "y": n["y"], "t0": t0, "t1": t1, "rueck": rueck}
        if grund:
            eintrag["grund"] = grund
        f.abschnitte.append(eintrag)

    # -- Ergebnis -------------------------------------------------------------------
    def laufen(self) -> dict:
        self.uhr.laufen()
        ressourcen = [self._ressource_auswerten(r) for r in self.flotten.values()]
        ressourcen += [self._aufzug_auswerten(a) for a in self.aufzuege.values()]
        ressourcen += [self._ressource_auswerten(r) for r in self.kanten.values()]
        ressourcen += [self._ressource_auswerten(r) for r in self.knoten.values()]
        engpaesse = sorted(
            (r for r in ressourcen if r["max_wartezeit"] >= 60 or r["spitze"] >= 0.9),
            key=lambda r: (r["max_wartezeit"], r["spitze"]),
            reverse=True,
        )
        fahrten = [self._fahrt_dict(f) for f in self.fahrten]
        return {
            "fahrten": fahrten,
            "ressourcen": ressourcen,
            "engpaesse": [{"typ": r["typ"], "id": r["id"]} for r in engpaesse],
            "fehler": self.fehler,
            "zusammenfassung": {
                "lieferungen": len({f.lieferung["id"] for f in self.fahrten}),
                "fahrten": len(fahrten),
                "verspaetet": sum(1 for f in fahrten if f["verspaetet"]),
                "nicht_fertig": sum(1 for f in fahrten if f["ende"] is None),
                "max_wartezeit": max((sum(f["warte"].values()) for f in fahrten), default=0),
                "summe_wartezeit": sum(sum(f["warte"].values()) for f in fahrten),
                "engpaesse": len(engpaesse),
            },
        }

    def _fahrt_dict(self, f: Fahrt) -> dict:
        l = f.lieferung
        spaetestens = zeit_in_sekunden(l["spaetestens"]) if l.get("spaetestens") and f.art == "hin" else None
        verspaetet = spaetestens is not None and (f.ankunft is None or f.ankunft > spaetestens)
        return {
            "id": f.id,
            "lieferung_id": l["id"],
            "name": l["name"],
            "lieferant": l["lieferant"],
            "richtung": ("entsorgung" if l["richtung"] == "versorgung" else "versorgung") if f.art == "spaeter" else l["richtung"],
            "art": f.art,
            "transportart_id": l["transportart_id"],
            "nr": f.nr,
            "von_n": f.von_n,
            "start_id": f.start_id,
            "ziel_id": f.ziel_id,
            "wagen": [w["name"] for w in f.wagen],
            "geplant": f.geplant,
            "start": f.start,
            "ankunft": f.ankunft,
            "fertig": f.fertig,
            "ende": f.ende,
            "spaetestens": spaetestens,
            "verspaetet": verspaetet,
            "warte": {k: round(v, 1) for k, v in f.warte.items()},
            "abschnitte": f.abschnitte,
        }

    @staticmethod
    def _raster(intervalle: list[tuple[float, float, float]], kapazitaet: float) -> list[list[float]]:
        """Mittlere Auslastung je 5 Minuten: Summe(Dauer × Menge) / (Raster × Kapazität)."""
        werte: dict[int, float] = {}
        for t0, t1, menge in intervalle:
            if t1 <= t0:
                continue
            b = int(t0 // RASTER)
            while b * RASTER < t1:
                s, e = max(t0, b * RASTER), min(t1, (b + 1) * RASTER)
                werte[b] = werte.get(b, 0.0) + (e - s) * menge
                b += 1
        return [[b * RASTER, round(v / (RASTER * kapazitaet), 3)] for b, v in sorted(werte.items())]

    def _ressource_auswerten(self, r: Ressource) -> dict:
        intervalle = [(t0, t1, belegt) for (t0, belegt, _), (t1, _, _) in zip(r.verlauf, r.verlauf[1:])]
        raster = self._raster(intervalle, r.kapazitaet or 1)
        return {
            "typ": r.typ,
            "id": r.rid,
            "name": r.name,
            "stockwerk_id": r.stockwerk_id,
            "kapazitaet": r.kapazitaet,
            "anzahl": len(r.wartezeiten),
            "max_wartezeit": round(max(r.wartezeiten, default=0.0), 1),
            "summe_wartezeit": round(sum(r.wartezeiten), 1),
            "max_schlange": max((w for _, _, w in r.verlauf), default=0),
            "spitze": max((v for _, v in raster), default=0.0),
            "raster": raster,
            "verlauf": [[round(t, 1), b, w] for t, b, w in r.verlauf],
        }

    def _aufzug_auswerten(self, a: Aufzug) -> dict:
        raster = self._raster([(s, e, 1) for s, e, *_ in a.fahrten], 1)
        return {
            "typ": "aufzug",
            "id": a.daten["id"],
            "name": a.daten["name"],
            "stockwerk_id": None,
            "kapazitaet": a.daten["plaetze"],
            "anzahl": len(a.wartezeiten),
            "fahrten": len(a.fahrten),
            "exklusiv": sum(1 for f in a.fahrten if f[4]),
            "zu_gross": a.zu_gross,
            "max_wartezeit": round(max(a.wartezeiten, default=0.0), 1),
            "summe_wartezeit": round(sum(a.wartezeiten), 1),
            "max_schlange": max((w for _, _, w in a.verlauf), default=0),
            "spitze": max((v for _, v in raster), default=0.0),
            "raster": raster,
            "verlauf": [[round(t, 1), b, w] for t, b, w in a.verlauf],
            "belegungen": [[round(s, 1), round(e, 1), n, int(x)] for s, e, _, n, x in a.fahrten],
        }
