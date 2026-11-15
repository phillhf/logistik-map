"""Wegenetz, Wegsuche, Regeln und Ablauf-Simulation über die Schnittstelle."""

from datetime import date

import pytest

from logistikmap.regeln import RegelFehler, gilt_am, normalisieren

MO_FR = [1, 2, 3, 4, 5]


@pytest.fixture
def haus(admin):
    """UG (Ebene -1) mit Rampe, 2. OG (Ebene 2) mit Lager, verbunden über einen Aufzug.

    Maßstab 0,05 m/Punkt: UG-Weg 60 m, OG-Weg 50 m. Aufzug 3 Etagen: 15 + 2·10 + 3·5 = 50 s.
    """
    c = admin
    gid = c.post("/api/gebaeudeteile", json={"name": "Haus A", "kuerzel": "A"}).json()["id"]
    ug = c.post("/api/stockwerke", json={"gebaeudeteil_id": gid, "name": "UG", "ebene": -1}).json()["id"]
    og = c.post("/api/stockwerke", json={"gebaeudeteil_id": gid, "name": "2. OG", "ebene": 2}).json()["id"]
    for sid in (ug, og):
        c.put(f"/api/stockwerke/{sid}/massstab", json={"meter_pro_punkt": 0.05})
    sd = c.get("/api/stammdaten").json()
    ta = {t["name"]: t for t in sd["transportarten"]}
    wt = {w["name"]: w for w in sd["wagentypen"]}
    auf = c.post("/api/aufzuege", json={"name": "Aufzug 1", "art": "aufzug", "plaetze": 2, "fahrzeit_etage": 5, "tuerzeit": 10,
                                         "raeumzeit": 20, "anfahrt": 15, "transportarten": []}).json()["id"]

    def knoten(sid, x, y, art="weg", name="", **kw):
        return c.post("/api/knoten", json={"stockwerk_id": sid, "x": x, "y": y, "art": art, "name": name, **kw}).json()["id"]

    rampe = knoten(ug, 0, 0, "start", "Rampe")
    flur = knoten(ug, 1000, 0)
    a_ug = knoten(ug, 1000, 200, "aufzug", "Aufzug 1 UG", aufzug_id=auf)
    a_og = knoten(og, 1000, 200, "aufzug", "Aufzug 1 OG", aufzug_id=auf)
    lager = knoten(og, 2000, 200, "ziel", "Wäschelager")
    for a, b in ((rampe, flur), (flur, a_ug), (a_og, lager)):
        assert c.post("/api/kanten", json={"von": a, "nach": b}).status_code == 200
    return {"c": c, "ug": ug, "og": og, "ta": ta, "wt": wt, "aufzug": auf, "rampe": rampe, "flur": flur, "lager": lager, "a_ug": a_ug}


def lieferung(h, **kw):
    daten = {
        "name": "Wäsche", "lieferant": "Wäscherei", "richtung": "versorgung",
        "transportart_id": h["ta"]["Materialtransportdienst"]["id"], "start_id": h["rampe"], "ziel_id": h["lager"],
        "uhrzeit": "08:00", "ladung": [{"wagentyp_id": h["wt"]["Wäschewagen"]["id"], "anzahl": 1}],
        "regel": {"wochentage": MO_FR}, "rueckweg": {"modus": "leer"},
    }
    daten.update(kw)
    r = h["c"].post("/api/lieferungen", json=daten)
    assert r.status_code == 200, r.text
    return r.json()["id"]


# --------------------------------------------------------------------------- Regeln
def test_regeln():
    r = normalisieren({"wochentage": MO_FR})
    assert r["feiertage"] == "ausser"
    fronleichnam = date(2026, 6, 4)  # Donnerstag
    assert not gilt_am(r, fronleichnam, ist_feiertag=True)
    assert gilt_am(r, date(2026, 6, 5), ist_feiertag=False)
    assert not gilt_am(r, date(2026, 6, 6), ist_feiertag=False)  # Samstag
    assert gilt_am({**r, "feiertage": "nur"}, date(2026, 6, 4), True)
    assert gilt_am({**r, "feiertage": "auch"}, date(2026, 6, 4), True)
    zeitraum = normalisieren({"wochentage": [1, 2, 3, 4, 5, 6, 7], "von": "2026-07-01", "bis": "2026-07-31", "ausnahmen": ["2026-07-15"]})
    assert not gilt_am(zeitraum, date(2026, 6, 30), False)
    assert gilt_am(zeitraum, date(2026, 7, 14), False)
    assert not gilt_am(zeitraum, date(2026, 7, 15), False)
    assert gilt_am(normalisieren({"wochentage": [], "zusatztage": ["2026-12-24"]}), date(2026, 12, 24), False)
    with pytest.raises(RegelFehler):
        normalisieren({"wochentage": [8]})
    with pytest.raises(RegelFehler):
        normalisieren({"von": "2026-02-01", "bis": "2026-01-01"})


# --------------------------------------------------------------------------- Netz & Weg
def test_weg_ueber_aufzug(haus):
    lid = lieferung(haus)
    w = haus["c"].get(f"/api/lieferungen/{lid}/weg").json()
    assert w["laenge_m"] == pytest.approx(110)
    assert w["dauer"] == pytest.approx(60 + 50 + 50)
    assert [a["typ"] for a in w["abschnitte"]] == ["weg", "weg", "aufzug", "weg"]
    assert w["abschnitte"][2]["etagen"] == 3


def test_fts_braucht_raeumzeit_und_sperre(haus):
    c = haus["c"]
    fts = haus["ta"]["FTS"]
    lid = lieferung(haus, transportart_id=fts["id"])
    w = c.get(f"/api/lieferungen/{lid}/weg").json()
    assert w["dauer"] == pytest.approx(110 / 0.8 + 50 + 20)
    # Flur für FTS sperren → kein Weg
    netz = c.get(f"/api/stockwerke/{haus['ug']}/netz").json()
    kante = next(k for k in netz["kanten"] if {k["von"], k["nach"]} == {haus["rampe"], haus["flur"]})
    c.put(f"/api/kanten/{kante['id']}", json={"gesperrt": [fts["id"]]})
    r = c.get(f"/api/lieferungen/{lid}/weg")
    assert r.status_code == 422 and r.json()["detail"]["code"] == "kein_weg"


def test_massstab_fehlt(haus):
    c = haus["c"]
    c.put(f"/api/stockwerke/{haus['og']}/massstab", json={"meter_pro_punkt": None})
    lid = lieferung(haus)
    r = c.get(f"/api/lieferungen/{lid}/weg").json()["detail"]
    assert r["code"] == "massstab_fehlt" and r["stockwerke"] == "2. OG"


def test_kante_teilen_und_netz(haus):
    c = haus["c"]
    netz = c.get(f"/api/stockwerke/{haus['ug']}/netz").json()
    kante = next(k for k in netz["kanten"] if {k["von"], k["nach"]} == {haus["rampe"], haus["flur"]})
    neu = c.post(f"/api/kanten/{kante['id']}/teilen", json={"x": 400, "y": 30}).json()
    assert (neu["x"], neu["y"]) == (400, 0)
    netz = c.get(f"/api/stockwerke/{haus['ug']}/netz").json()
    assert len(netz["kanten"]) == 3
    assert any(k["id"] == neu["id"] for k in netz["knoten"])
    # Weg bleibt gleich lang
    lid = lieferung(haus)
    assert c.get(f"/api/lieferungen/{lid}/weg").json()["laenge_m"] == pytest.approx(110)


def test_flaechen_und_zuordnung(haus):
    c = haus["c"]
    bereich = c.post("/api/flaechen", json={"stockwerk_id": haus["og"], "art": "bereich", "name": "Versorgung",
                                            "punkte": [[1500, 0], [2500, 0], [2500, 500], [1500, 500]]}).json()
    raum = c.post("/api/flaechen", json={"stockwerk_id": haus["og"], "art": "raum", "name": "Wäschelager", "nummer": "2.105",
                                         "punkte": [[1900, 100], [2100, 100], [2100, 300], [1900, 300]]}).json()
    assert raum["parent_id"] == bereich["id"]
    punkte = {p["id"]: p for p in c.get("/api/punkte").json()}
    assert punkte[haus["lager"]]["flaeche"] == "Wäschelager"
    assert c.post("/api/flaechen", json={"stockwerk_id": haus["og"], "name": "x", "punkte": [[0, 0], [1, 1]]}).status_code == 400


def test_in_verwendung(haus):
    c = haus["c"]
    lieferung(haus)
    assert c.delete(f"/api/knoten/{haus['rampe']}").json()["detail"]["code"] == "knoten_in_verwendung"
    assert c.delete(f"/api/transportarten/{haus['ta']['Materialtransportdienst']['id']}").status_code == 409
    assert c.delete(f"/api/stockwerke/{haus['ug']}").json()["detail"]["code"] == "in_verwendung"


def test_lieferung_pruefung(haus):
    c = haus["c"]
    basis = {"name": "x", "transportart_id": haus["ta"]["FTS"]["id"], "start_id": haus["rampe"], "ziel_id": haus["lager"], "uhrzeit": "8:00"}
    assert c.post("/api/lieferungen", json=basis).json()["detail"]["code"] == "uhrzeit_ungueltig"
    assert c.post("/api/lieferungen", json={**basis, "uhrzeit": "08:00", "ziel_id": haus["rampe"]}).json()["detail"]["code"] == "start_gleich_ziel"
    r = c.post("/api/lieferungen", json={**basis, "uhrzeit": "08:00", "rueckweg": {"modus": "spaeter"}})
    assert r.json()["detail"]["code"] == "rueckweg_uhrzeit_fehlt"


# --------------------------------------------------------------------------- Simulation
FREITAG = "2026-06-05"


def sim(h, datum=FREITAG):
    r = h["c"].get(f"/api/simulation?datum={datum}")
    assert r.status_code == 200, r.text
    return r.json()


def test_eine_fahrt_ohne_warten(haus):
    lieferung(haus, rueckweg={"modus": "keiner"})
    e = sim(haus)
    assert e["zusammenfassung"]["fahrten"] == 1
    f = e["fahrten"][0]
    lade, entlade = 90, 90
    assert f["ankunft"] == pytest.approx(8 * 3600 + lade + 160)
    assert f["ende"] == pytest.approx(f["ankunft"] + entlade)
    assert sum(f["warte"].values()) == 0
    assert e["engpaesse"] == []
    typen = [a["typ"] for a in f["abschnitte"]]
    assert typen == ["laden", "weg", "weg", "aufzug", "weg", "entladen"]


def test_zwanzig_wagen_um_acht_stauen_am_aufzug(haus):
    """Das Beispiel aus dem Konzept: 20 Wagen gleichzeitig aus dem UG nach oben."""
    lieferung(haus, ladung=[{"wagentyp_id": haus["wt"]["Wäschewagen"]["id"], "anzahl": 20}], spaetestens="08:10")
    e = sim(haus)
    assert e["zusammenfassung"]["fahrten"] == 20
    aufzug = next(r for r in e["ressourcen"] if r["typ"] == "aufzug")
    # 2 Plätze: 10 Fahrten nach oben, dazu leere Rückfahrten
    assert aufzug["max_wartezeit"] == pytest.approx(9 * 50)  # letztes Paar wartet 9 Aufzugfahrten
    assert {"typ": "aufzug", "id": haus["aufzug"]} in e["engpaesse"]
    assert e["zusammenfassung"]["verspaetet"] > 0
    assert aufzug["spitze"] == pytest.approx(1.0)
    # gemeinsam fahrende Wagen: höchstens 2 je Fahrt
    assert max(b[2] for b in aufzug["belegungen"]) == 2


def test_fts_flotte_und_exklusiv(haus):
    fts = haus["ta"]["FTS"]
    haus["c"].put(f"/api/transportarten/{fts['id']}", json={**fts, "anzahl": 1})
    lieferung(haus, transportart_id=fts["id"], ladung=[{"wagentyp_id": haus["wt"]["Rollcontainer"]["id"], "anzahl": 2}])
    e = sim(haus)
    f1, f2 = e["fahrten"]
    assert f2["warte"]["fahrzeug"] > 0
    assert f2["start"] == pytest.approx(f1["ende"])
    aufzug = next(r for r in e["ressourcen"] if r["typ"] == "aufzug")
    assert aufzug["exklusiv"] == aufzug["fahrten"] == 4  # hin und zurück, je allein


def test_regel_und_feiertag_in_simulation(haus):
    lieferung(haus)
    assert sim(haus, "2026-06-04")["zusammenfassung"]["fahrten"] == 0  # Fronleichnam (NRW)
    assert sim(haus, "2026-06-04")["feiertag"] == "fronleichnam"
    assert sim(haus, "2026-06-05")["zusammenfassung"]["fahrten"] == 1
    assert sim(haus, "2026-06-06")["zusammenfassung"]["fahrten"] == 0


def test_rueckweg_spaeter_und_beladen(haus):
    lieferung(haus, rueckweg={"modus": "spaeter", "uhrzeit": "14:00"})
    lieferung(haus, name="Speisen", uhrzeit="11:00", rueckweg={"modus": "beladen"})
    e = sim(haus)
    arten = sorted((f["name"], f["art"], f["richtung"]) for f in e["fahrten"])
    assert ("Wäsche", "spaeter", "entsorgung") in arten
    speisen = next(f for f in e["fahrten"] if f["name"] == "Speisen")
    assert [a["typ"] for a in speisen["abschnitte"]].count("entladen") == 2
    assert any(a.get("rueck") for a in speisen["abschnitte"])


def test_engstelle_rampe(haus):
    c = haus["c"]
    c.put(f"/api/knoten/{haus['rampe']}", json={"kapazitaet": 1})
    lieferung(haus, ladung=[{"wagentyp_id": haus["wt"]["Wäschewagen"]["id"], "anzahl": 3}], rueckweg={"modus": "keiner"})
    e = sim(haus)
    rampe = next(r for r in e["ressourcen"] if r["typ"] == "knoten")
    assert rampe["max_wartezeit"] == pytest.approx(180)  # dritter Wagen wartet zwei Ladezeiten
    assert sorted(f["warte"]["engstelle"] for f in e["fahrten"]) == pytest.approx([0, 90, 180])


def test_fehlerhafte_lieferung_wird_gemeldet(haus):
    c = haus["c"]
    c.put(f"/api/stockwerke/{haus['og']}/massstab", json={"meter_pro_punkt": None})
    lieferung(haus)
    e = sim(haus)
    assert e["zusammenfassung"]["fahrten"] == 0
    assert e["fehler"][0]["code"] == "massstab_fehlt"


def test_kalender(haus):
    lid = lieferung(haus)
    k = haus["c"].get("/api/kalender?von=2026-06-01&tage=7").json()
    an = [t["datum"] for t in k if lid in t["lieferungen"]]
    assert an == ["2026-06-01", "2026-06-02", "2026-06-03", "2026-06-05"]
    assert k[3]["feiertag"] == "fronleichnam"
