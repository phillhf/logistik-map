"""Erste Schritte: prüft, was zum Einrichten noch fehlt.

Die Seite „Erste Schritte“ führt durch die Einrichtung. Jeder Schritt wird aus den Daten
geprüft, niemand muss etwas abhaken (bis auf zwei Bestätigungen: Bundesland und Stammdaten,
weil dort sinnvolle Vorgaben schon eingetragen sind).

Ein Schritt hat den Status
  "offen"    – Grundlage fehlt oder es gibt Fehler, die das Rechnen verhindern,
  "hinweis"  – erledigt, aber es gibt etwas zu prüfen,
  "erledigt" – nichts zu tun.
Probleme tragen einen Code (Text in i18n unter einrichtung.problem.<code>), Platzhalter und
einen Link an die Stelle, an der man es behebt.
"""

from __future__ import annotations

import json

from fastapi import Depends, FastAPI, Request
from pydantic import BaseModel

from .db import Datenbank
from .netz import BENANNTE_ARTEN, Netz, WegFehler

MAX_PROBLEME = 12  # je Schritt; der Rest wird nur gezählt
PUNKT_ARTEN = ("start", "ziel", "punkt")


class Bestaetigung(BaseModel):
    schritt: str


def _problem(code: str, art: str = "fehler", link: str | None = None, **werte) -> dict:
    return {"code": code, "art": art, "link": link, "werte": werte}


def _schritt(sid: str, grundlage: bool, probleme: list[dict], link: str, **zahlen) -> dict:
    if not grundlage or any(p["art"] == "fehler" for p in probleme):
        status = "offen"
    elif probleme:
        status = "hinweis"
    else:
        status = "erledigt"
    mehr = max(0, len(probleme) - MAX_PROBLEME)
    # Fehler zuerst zeigen
    probleme = sorted(probleme, key=lambda p: p["art"] != "fehler")[:MAX_PROBLEME]
    return {"id": sid, "status": status, "probleme": probleme, "weitere": mehr, "link": link, "zahlen": zahlen}


def pruefen(db: Datenbank, https: bool = False) -> dict:
    teile = db.alle("SELECT * FROM gebaeudeteile ORDER BY reihenfolge, name")
    teil_namen = {t["id"]: t["kuerzel"] or t["name"] for t in teile}
    stockwerke = db.alle(
        """SELECT s.*, p.status AS plan_status, p.fehler AS plan_fehler
             FROM stockwerke s JOIN gebaeudeteile g ON g.id = s.gebaeudeteil_id
             LEFT JOIN plaene p ON p.id = s.plan_id
            ORDER BY g.reihenfolge, g.name, s.ebene DESC, s.name"""
    )
    mehrere_teile = len(teile) > 1

    def sw_name(s: dict) -> str:
        return f"{s['name']} ({teil_namen.get(s['gebaeudeteil_id'], '')})" if mehrere_teile else s["name"]

    schritte = []

    # 1 – Bundesland (Feiertage)
    schritte.append(_schritt(
        "bundesland", bool(db.einstellung("bundesland_bestaetigt", False)), [], "#/einstellungen",
        bundesland=db.einstellung("bundesland", "NW"),
    ))

    # 2 – Gebäudeteile und Stockwerke
    probleme = [
        _problem("teil_ohne_stockwerke", link="#/gebaeude", teil=t["name"])
        for t in teile
        if not any(s["gebaeudeteil_id"] == t["id"] for s in stockwerke)
    ]
    schritte.append(_schritt("gebaeude", bool(stockwerke), probleme, "#/gebaeude", teile=len(teile), stockwerke=len(stockwerke)))

    # 3 – PDF-Pläne
    probleme = []
    for s in stockwerke:
        if s["plan_id"] is None:
            probleme.append(_problem("kein_plan", link="#/gebaeude", stockwerk=sw_name(s)))
        elif s["plan_status"] == "fehler":
            probleme.append(_problem("plan_fehler", link="#/gebaeude", stockwerk=sw_name(s), fehler=s["plan_fehler"] or ""))
        elif s["plan_status"] != "fertig":
            probleme.append(_problem("plan_laeuft", art="hinweis", link="#/gebaeude", stockwerk=sw_name(s)))
    fertig = [s for s in stockwerke if s["plan_status"] == "fertig"]
    schritte.append(_schritt(
        "plaene", bool(fertig), probleme, "#/gebaeude",
        mit_plan=len(fertig), stockwerke=len(stockwerke), dokumente=db.eins("SELECT COUNT(*) AS n FROM dokumente")["n"],
    ))

    # 4 – Maßstab
    probleme = [
        _problem("massstab_fehlt", link=f"#/karte/{s['id']}/bearbeiten/massstab", stockwerk=sw_name(s))
        for s in fertig
        if not s["meter_pro_punkt"]
    ]
    schritte.append(_schritt("massstab", bool(fertig), probleme, f"#/karte/{fertig[0]['id']}/bearbeiten/massstab" if fertig else "#/gebaeude"))

    # 5 – Karte zeichnen: Wege, Punkte, Aufzüge, Übergänge
    netz = Netz(db)
    probleme = []
    kanten_je_sw: dict[int, int] = {}
    for k in netz.kanten.values():
        for n in {k["von"], k["nach"]}:
            if n in netz.knoten:
                sw = netz.knoten[n]["stockwerk_id"]
                kanten_je_sw[sw] = kanten_je_sw.get(sw, 0) + 1
    for s in fertig:
        if s["meter_pro_punkt"] and not kanten_je_sw.get(s["id"]):
            probleme.append(_problem("keine_wege", art="hinweis", link=f"#/karte/{s['id']}/bearbeiten/werkzeug/weg", stockwerk=sw_name(s)))
    sw_index = {s["id"]: s for s in stockwerke}
    benannt = [k for k in netz.knoten.values() if k["art"] in BENANNTE_ARTEN]
    punkte = [k for k in benannt if k["art"] in PUNKT_ARTEN]

    def knoten_link(k: dict) -> str:
        return f"#/karte/{k['stockwerk_id']}/bearbeiten/knoten/{k['id']}"

    def knoten_werte(k: dict) -> dict:
        s = sw_index.get(k["stockwerk_id"])
        return {"name": k["name"] or "?", "stockwerk": sw_name(s) if s else ""}

    ohne_weg = set()
    for k in benannt:
        if not netz.nachbarn.get(k["id"]):
            ohne_weg.add(k["id"])
            probleme.append(_problem("punkt_ohne_weg", link=knoten_link(k), **knoten_werte(k)))
        elif k["art"] == "uebergang" and not any(
            netz.knoten[n]["stockwerk_id"] != k["stockwerk_id"] for n, _ in netz.nachbarn[k["id"]]
        ):
            probleme.append(_problem("uebergang_offen", art="hinweis", link=knoten_link(k), **knoten_werte(k)))
    for aid, auf in netz.aufzuege.items():
        halte = netz.aufzug_halte.get(aid, [])
        if len(halte) == 1:
            k = netz.knoten[halte[0]]
            probleme.append(_problem("aufzug_ein_halt", link=knoten_link(k), aufzug=auf["name"], stockwerk=knoten_werte(k)["stockwerk"]))

    # Zusammenhang: Stockwerke oder Punkte, die vom übrigen Netz getrennt sind
    if punkte:
        gruppen: list[set[int]] = []
        rest = {k["id"] for k in netz.knoten.values()}
        while rest:
            g, _, _ = netz.erreichbar(next(iter(rest)))
            gruppen.append(g)
            rest -= g
        punkt_ids = {k["id"] for k in punkte}
        haupt = max(gruppen, key=lambda g: (len(g & punkt_ids), len(g)))
        haupt_sw = {netz.knoten[n]["stockwerk_id"] for n in haupt}
        mit_netz = {sw for sw, n in kanten_je_sw.items() if n}
        getrennt_sw = {sw for sw in mit_netz if sw not in haupt_sw}
        if len(mit_netz) > 1:
            for sw in sorted(getrennt_sw, key=lambda x: list(sw_index).index(x) if x in sw_index else 0):
                if sw in sw_index:
                    probleme.append(_problem("stockwerk_getrennt", art="hinweis", link=f"#/karte/{sw}/bearbeiten", stockwerk=sw_name(sw_index[sw])))
        for k in punkte:
            if k["id"] not in haupt and k["id"] not in ohne_weg and k["stockwerk_id"] not in getrennt_sw:
                probleme.append(_problem("punkt_getrennt", art="hinweis", link=knoten_link(k), **knoten_werte(k)))
    if len(punkte) < 2 and fertig:
        probleme.append(_problem("zu_wenig_punkte", link=f"#/karte/{fertig[0]['id']}/bearbeiten/werkzeug/punkt", anzahl=len(punkte)))
    schritte.append(_schritt(
        "karte", bool(netz.kanten) and len(punkte) >= 2, probleme,
        f"#/karte/{fertig[0]['id']}/bearbeiten" if fertig else "#/gebaeude",
        wege=len(netz.kanten), punkte=len(punkte), aufzuege=len(netz.aufzug_halte),
    ))

    # 6 – Stammdaten: Transportarten, Wagentypen, Aufzugzeiten
    transportarten = db.alle("SELECT * FROM transportarten ORDER BY id")
    wagentypen = db.alle("SELECT id FROM wagentypen")
    probleme = []
    if not transportarten:
        probleme.append(_problem("keine_transportart", link="#/stammdaten"))
    for ta in transportarten:
        if not ta["anzahl"] and not json.loads(ta.get("schichten") or "[]"):
            probleme.append(_problem("anzahl_unbegrenzt", art="hinweis", link="#/stammdaten", name=ta["name"]))
    for aid, auf in netz.aufzuege.items():
        if not netz.aufzug_halte.get(aid):
            probleme.append(_problem("aufzug_nicht_eingezeichnet", art="hinweis", link="#/stammdaten", aufzug=auf["name"]))
    bestaetigt = bool(db.einstellung("stammdaten_bestaetigt", False))
    schritte.append(_schritt(
        "stammdaten", bestaetigt and bool(transportarten) and bool(wagentypen), probleme, "#/stammdaten",
        transportarten=len(transportarten), wagentypen=len(wagentypen), aufzuege=len(netz.aufzuege), bestaetigt=bestaetigt,
    ))

    # 7 – Lieferungen: gibt es für jede einen Weg?
    lieferungen = db.alle("SELECT id, name, transportart_id, start_id, ziel_id, via, rueckweg FROM lieferungen WHERE aktiv = 1 ORDER BY uhrzeit, name")
    ta_index = {t["id"]: t for t in transportarten}
    probleme = []
    for l in lieferungen:
        ta = ta_index.get(l["transportart_id"])
        if ta is None:
            continue
        rueck = json.loads(l["rueckweg"] or "{}")
        strecken = [(l["start_id"], l["ziel_id"], json.loads(l["via"] or "[]"))]
        if rueck.get("modus", "leer") != "keiner":
            strecken.append((l["ziel_id"], rueck.get("ziel_id") or l["start_id"], []))
        for von, nach, via in strecken:
            try:
                netz.weg(von, nach, ta, via)
            except WegFehler as e:
                werte = {"lieferung": l["name"], "von": netz.knoten.get(von, {}).get("name") or "?", "nach": netz.knoten.get(nach, {}).get("name") or "?", "transportart": ta["name"]}
                if e.code == "massstab_fehlt":
                    probleme.append(_problem("lieferung_massstab", link=None, stockwerke=e.extra.get("stockwerke", ""), **werte))
                else:
                    d = netz.weg_diagnose(von, nach, ta, teil_namen if mehrere_teile else None)
                    code = d.pop("code")
                    # Link dorthin, wo man es behebt: Lücke im Netz → Karte, Aufzug nicht erlaubt → Stammdaten
                    sw = d.pop("stockwerk_id", None)
                    link = f"#/karte/{sw}/bearbeiten" if sw else "#/stammdaten" if code == "aufzug_nicht_erlaubt" else f"#/lieferungen/{l['id']}"
                    probleme.append(_problem(f"lieferung_{code}", link=link, **werte, **d))
                break
    schritte.append(_schritt("lieferungen", bool(lieferungen), probleme, "#/lieferungen", lieferungen=len(lieferungen)))

    pflicht = len(schritte)
    erledigt = sum(1 for s in schritte if s["status"] != "offen")

    # Ergebnis ansehen (kein Haken, nur Wegweiser)
    bereit = all(s["status"] != "offen" for s in schritte)
    schritte.append({"id": "ergebnis", "status": "bereit" if bereit else "gesperrt", "probleme": [], "weitere": 0,
                     "link": f"#/karte/{fertig[0]['id']}/ablauf" if fertig else "#/auswertung", "zahlen": {}})

    ldap = db.einstellung("ldap", {}) or {}
    optional = [
        {"id": "benutzer", "erledigt": db.eins("SELECT COUNT(*) AS n FROM benutzer")["n"] > 1, "link": "#/benutzer"},
        {"id": "ad", "erledigt": bool(ldap.get("aktiv")), "link": "#/einstellungen"},
        {"id": "https", "erledigt": https, "link": "#/einstellungen"},
    ]
    return {"schritte": schritte, "erledigt": erledigt, "gesamt": pflicht, "fertig": bereit, "optional": optional}


def registrieren(app: FastAPI, db: Datenbank, fehler, bearbeiten, verwalten) -> None:

    @app.get("/api/einrichtung")
    def einrichtung(request: Request, _: dict = Depends(bearbeiten)):
        return pruefen(db, https=request.url.scheme == "https")

    @app.post("/api/einrichtung/bestaetigen")
    def bestaetigen(d: Bestaetigung, benutzer: dict = Depends(bearbeiten)):
        if d.schritt == "stammdaten":
            db.setze_einstellung("stammdaten_bestaetigt", True)
        elif d.schritt == "bundesland":
            if "verwalten" not in benutzer.get("rechte", []):
                raise fehler(403, "keine_berechtigung")
            db.setze_einstellung("bundesland_bestaetigt", True)
        else:
            raise fehler(400, "schritt_unbekannt")
        return {"ok": True}
