"""Produktion: Takt, Stellplätze, Abholregeln, Rückstau, Verteilung, Szenario, Mindestbedarf."""

import io

import pytest
from openpyxl import load_workbook

from logistikmap.simulation import produktion_stueck, produktion_ziele
from test_planung import FREITAG, haus, lieferung, sim  # noqa: F401

MO_FR = [1, 2, 3, 4, 5]


def uhr(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 3600 + int(m) * 60


def daten(h, **kw):
    d = {
        "name": "Küche", "knoten_id": h["rampe"], "transportart_id": h["ta"]["Materialtransportdienst"]["id"],
        "wagentyp_id": h["wt"]["Speisenwagen"]["id"], "von": "06:30", "bis": "08:00", "takt": 8, "menge": 1,
        "abholung": {"art": "sofort"}, "verteilung": [{"ziel_id": h["lager"], "anzahl": 1}],
        "regel": {"wochentage": MO_FR}, "rueckweg": {"modus": "leer"},
    }
    d.update(kw)
    return d


def produktion(h, **kw):
    r = h["c"].post("/api/produktionen", json=daten(h, **kw))
    assert r.status_code == 200, r.text
    return r.json()["id"]


def fahrzeuge(h, anzahl, pro_fahrt=1, **kw):
    ta = h["ta"]["Materialtransportdienst"]
    assert h["c"].put(f"/api/transportarten/{ta['id']}", json={**ta, "anzahl": anzahl, "wagen_pro_fahrt": pro_fahrt, "schichten": [], **kw}).status_code == 200


def zweites_ziel(h):
    c = h["c"]
    kid = c.post("/api/knoten", json={"stockwerk_id": h["ug"], "x": 1000, "y": -400, "art": "ziel", "name": "Station UG"}).json()["id"]
    assert c.post("/api/kanten", json={"von": h["flur"], "nach": kid}).status_code == 200
    return kid


def test_stueckzahl_und_verteilung():
    p = {"von": "06:30", "bis": "08:00", "takt": 8, "menge": 1}
    assert produktion_stueck(p) == 12  # 06:30 … 07:58
    assert produktion_stueck({**p, "takt": 10}) == 10  # der letzte genau um 08:00
    assert produktion_stueck({**p, "takt": 10, "menge": 3}) == 30
    assert produktion_stueck({"von": "23:30", "bis": "00:30", "takt": 30, "menge": 1}) == 3  # über Mitternacht
    assert produktion_stueck({"von": "07:00", "bis": "07:00", "takt": 5, "menge": 4}) == 4  # alles auf einmal
    verteilung = {"verteilung": [{"ziel_id": 1, "anzahl": 3}, {"ziel_id": 2, "anzahl": 2}]}
    assert produktion_ziele(verteilung, 7) == [1, 1, 1, 2, 2, 1, 1]


def test_takt_erzeugt_fahrten(haus):
    produktion(haus)
    e = sim(haus)
    p = e["produktionen"][0]
    assert p["gesamt"] == p["fertig"] == p["abgeholt"] == 12
    assert p["erster"] == uhr("06:30") and p["letzter"] == p["letzter_plan"] == uhr("07:58")
    assert p["stillstand"] == 0 and p["max_standzeit"] == 0
    assert [f["geplant"] for f in e["fahrten"]] == [uhr("06:30") + i * 480 for i in range(12)]
    assert e["zusammenfassung"]["lieferungen"] == 0 and e["zusammenfassung"]["produktionen"] == 1
    assert all(f["wagen"] == ["Speisenwagen"] and f["von_n"] == 12 for f in e["fahrten"])
    assert all(f["produktion_id"] == p["id"] and f["lieferung_id"] < 0 for f in e["fahrten"])
    # am Wochenende nicht
    assert sim(haus, "2026-06-06")["produktionen"] == []


def test_verteilung_auf_mehrere_ziele(haus):
    station = zweites_ziel(haus)
    produktion(haus, verteilung=[{"ziel_id": haus["lager"], "anzahl": 3}, {"ziel_id": station, "anzahl": 1}])
    ziele = [f["ziel_id"] for f in sim(haus)["fahrten"]]
    assert ziele.count(haus["lager"]) == 9 and ziele.count(station) == 3
    assert ziele[:4] == [haus["lager"]] * 3 + [station]


def test_rueckstau_haelt_produktion_an(haus):
    """Ein Transporteur schafft den Takt nicht: Stellplätze voll, Produktion steht, Menge wird trotzdem fertig."""
    fahrzeuge(haus, 1)
    produktion(haus, takt=2, bis="07:00", stellplaetze=3)
    e = sim(haus)
    p = e["produktionen"][0]
    assert p["gesamt"] == p["fertig"] == p["abgeholt"] == 16
    assert p["stillstand"] > 0 and p["stillstaende"]
    assert p["letzter"] > p["letzter_plan"] == uhr("07:00")
    assert p["max_wartend"] == 3  # nie mehr, als Stellplätze da sind
    r = next(r for r in e["ressourcen"] if r["typ"] == "puffer")
    assert r["kapazitaet"] == 3 and r["summe_wartezeit"] == pytest.approx(p["stillstand"], abs=0.2)
    assert {"typ": "puffer", "id": p["id"]} in e["engpaesse"]
    # ohne Grenze staut es sich, aber nichts steht
    haus["c"].put(f"/api/produktionen/{p['id']}", json=daten(haus, takt=2, bis="07:00"))
    frei = sim(haus)["produktionen"][0]
    assert frei["stillstand"] == 0 and frei["letzter"] == frei["letzter_plan"] and frei["max_wartend"] > 3
    assert not [r for r in sim(haus)["ressourcen"] if r["typ"] == "puffer"]


def test_stellplatz_wird_erst_nach_dem_laden_frei(haus):
    fahrzeuge(haus, 0, ladezeit=300)
    produktion(haus, takt=1, bis="06:31", stellplaetze=1)
    p = sim(haus)["produktionen"][0]
    # Wagen 1 ab 06:30, geladen bis 06:35; Wagen 2 wäre 06:31 fertig und wartet 4 min auf den Platz
    assert p["stillstaende"] == [[uhr("06:31"), uhr("06:35")]]
    assert p["letzter"] == uhr("06:35")


def test_abholung_ab_menge(haus):
    fahrzeuge(haus, 0, pro_fahrt=4)
    produktion(haus, takt=5, bis="07:15", abholung={"art": "menge", "menge": 4})  # 10 Wagen
    e = sim(haus)
    # nach dem 4. (06:45) und dem 8. (07:05); der Rest, sobald alles fertig ist (07:15)
    assert [(f["geplant"], len(f["wagen"])) for f in e["fahrten"]] == [(uhr("06:45"), 4), (uhr("07:05"), 4), (uhr("07:15"), 2)]
    assert e["produktionen"][0]["max_standzeit"] == 15 * 60


def test_volle_stellplaetze_rufen_auch_vor_der_menge(haus):
    """5 Plätze, 2 je Takt, Abholung ab 5: Der dritte Takt passt nicht mehr – ohne Abruf stünde es ewig."""
    fahrzeuge(haus, 0)
    produktion(haus, takt=10, bis="07:30", menge=2, stellplaetze=5, abholung={"art": "menge", "menge": 5})
    p = sim(haus)["produktionen"][0]
    assert p["fertig"] == p["abgeholt"] == p["gesamt"] == 14


def test_abholung_zu_festen_zeiten(haus):
    fahrzeuge(haus, 0)
    produktion(haus, takt=10, bis="07:30", abholung={"art": "zeiten", "zeiten": ["07:00", "07:30"]})  # 7 Wagen
    e = sim(haus)
    # um 07:00 sind 4 fertig (der vierte genau dann), um 07:30 die restlichen 3
    assert [f["geplant"] for f in e["fahrten"]] == [uhr("07:00")] * 4 + [uhr("07:30")] * 3
    assert e["zusammenfassung"]["nicht_abgeholt"] == 0


def test_nicht_abgeholt_und_steht_bis_tagesende(haus):
    fahrzeuge(haus, 0)
    produktion(haus, takt=10, bis="07:30", stellplaetze=2, abholung={"art": "zeiten", "zeiten": ["07:00"]})
    e = sim(haus)
    p = e["produktionen"][0]
    assert p["abgeholt"] == 2 and p["fertig"] == 4 and p["letzter"] is None
    assert p["stillstaende"][-1][1] is None  # steht noch
    assert e["zusammenfassung"]["nicht_abgeholt"] == 5
    assert p["stillstand"] > 12 * 3600


def test_fahrzeug_nimmt_inzwischen_fertige_mit(haus):
    """Ein Fahrzeug für zwei Wagen: Während es unterwegs ist, wird mehr fertig – die nächste Fahrt ist voll."""
    fahrzeuge(haus, 1, pro_fahrt=2)
    produktion(haus, takt=2, bis="07:00")  # 16 Wagen
    e = sim(haus)
    assert sum(len(f["wagen"]) for f in e["fahrten"]) == 16
    assert all(1 <= len(f["wagen"]) <= 2 for f in e["fahrten"])
    assert len(e["fahrten"]) < 16
    assert e["zusammenfassung"]["nicht_fertig"] == 0


def test_spaeter_zurueck_und_verspaetung(haus):
    produktion(haus, takt=30, rueckweg={"modus": "spaeter", "uhrzeit": "13:00"}, spaetestens="06:45")  # 4 Wagen
    e = sim(haus)
    rueck = [f for f in e["fahrten"] if f["art"] == "spaeter"]
    assert len(rueck) == 4 and all(f["geplant"] == uhr("13:00") and f["ziel_id"] == haus["rampe"] for f in rueck)
    hin = [f for f in e["fahrten"] if f["art"] == "hin"]
    assert [f["verspaetet"] for f in hin] == [False, True, True, True]


def test_ueber_mitternacht(haus):
    produktion(haus, von="23:00", bis="01:00", takt=30, spaetestens="02:00", regel={"wochentage": MO_FR + [6, 7], "feiertage": "auch"})
    e = sim(haus)
    assert e["produktionen"][0]["gesamt"] == 5
    heute = [f for f in e["fahrten"] if not f["vortag"]]
    assert len(heute) == 5 and not any(f["verspaetet"] for f in heute)
    # der Lauf vom Vortag reicht in den Morgen
    assert any(f["vortag"] and f["geplant"] >= 0 for f in e["fahrten"])
    assert e["zusammenfassung"]["produktionen"] == 1


def test_teilt_sich_fahrzeuge_mit_lieferungen(haus):
    fahrzeuge(haus, 1)
    lieferung(haus, uhrzeit="06:29")
    produktion(haus, bis="06:30")
    f = next(f for f in sim(haus)["fahrten"] if f["produktion_id"])
    assert f["warte"]["fahrzeug"] > 0


def test_ohne_weg_wird_gemeldet(haus):
    insel = haus["c"].post("/api/knoten", json={"stockwerk_id": haus["ug"], "x": 0, "y": 900, "art": "ziel", "name": "Insel"}).json()["id"]
    pid = produktion(haus, verteilung=[{"ziel_id": insel, "anzahl": 1}, {"ziel_id": haus["lager"], "anzahl": 1}])
    e = sim(haus)
    assert [f["produktion_id"] for f in e["fehler"]] == [pid]
    assert e["produktionen"][0]["gesamt"] == 6  # das erreichbare Ziel läuft weiter
    schritt = next(s for s in haus["c"].get("/api/einrichtung").json()["schritte"] if s["id"] == "lieferungen")
    assert any(p["code"].startswith("lieferung_") for p in schritt["probleme"])


@pytest.mark.parametrize("aenderung, code", [
    ({"verteilung": []}, "produktion_ohne_ziel"),
    ({"von": "25:00"}, "uhrzeit_ungueltig"),
    ({"abholung": {"art": "zeiten", "zeiten": []}}, "abholung_zeiten_fehlen"),
    ({"abholung": {"art": "irgendwas"}}, "abholung_ungueltig"),
    ({"menge": 4, "stellplaetze": 3}, "stellplaetze_zu_wenig"),
    ({"stellplaetze": 3, "abholung": {"art": "menge", "menge": 4}}, "abholmenge_zu_gross"),
    ({"takt": 0.1, "bis": "22:00"}, "produktion_zu_viel"),
    ({"wagentyp_id": 9999}, "wagentyp_unbekannt"),
    ({"rueckweg": {"modus": "spaeter"}}, "rueckweg_uhrzeit_fehlt"),
])
def test_pruefung(haus, aenderung, code):
    r = haus["c"].post("/api/produktionen", json=daten(haus, **aenderung))
    assert r.status_code == 400 and r.json()["detail"]["code"] == code


def test_ort_und_verwendung(haus):
    c = haus["c"]
    assert c.post("/api/produktionen", json=daten(haus, knoten_id=haus["a_ug"])).json()["detail"]["code"] == "produktion_ort"
    c.put(f"/api/knoten/{haus['rampe']}", json={"art": "produktion", "name": "Küche"})
    schritt = next(s for s in c.get("/api/einrichtung").json()["schritte"] if s["id"] == "lieferungen")
    assert [p["code"] for p in schritt["probleme"]] == ["produktion_leer"]
    pid = produktion(haus, name="", transportart_id=None)
    p = c.get("/api/produktionen").json()[0]
    assert p["name"] == "Küche" and p["gesamt"] == 12 and p["transportart_id"]
    for kid in (haus["rampe"], haus["lager"]):
        assert c.delete(f"/api/knoten/{kid}").json()["detail"]["code"] == "knoten_in_produktion"
    assert c.delete(f"/api/transportarten/{p['transportart_id']}").status_code == 409
    assert c.delete(f"/api/wagentypen/{p['wagentyp_id']}").status_code == 409
    assert c.delete(f"/api/produktionen/{pid}").status_code == 200
    assert c.get("/api/produktionen").json() == []


def test_szenario_und_uebernehmen(haus):
    c = haus["c"]
    fahrzeuge(haus, 1)
    pid = produktion(haus, takt=2, bis="07:00", stellplaetze=3)
    sid = c.post("/api/szenarien", json={"name": "Mehr Platz", "aenderungen": {"produktionen": {str(pid): {"stellplaetze": 20, "takt": 3}}}}).json()["id"]
    e = c.get(f"/api/simulation?datum={FREITAG}&szenario={sid}").json()
    assert e["produktionen"][0]["stillstand"] == 0 and e["produktionen"][0]["gesamt"] == 11
    assert sim(haus)["produktionen"][0]["stillstand"] > 0  # Ist-Zustand unverändert
    assert c.post(f"/api/szenarien/{sid}/uebernehmen").status_code == 200
    p = c.get("/api/produktionen").json()[0]
    assert p["stellplaetze"] == 20 and p["takt"] == 3
    r = c.put(f"/api/szenarien/{sid}", json={"name": "x", "aenderungen": {"produktionen": {str(pid): {"takt": 0}}}})
    assert r.json()["detail"]["code"] == "szenario_ungueltig"


def test_mindestbedarf_produktion(haus):
    c = haus["c"]
    fahrzeuge(haus, 1)
    pid = produktion(haus, takt=2, bis="07:00", stellplaetze=3)
    r = c.get(f"/api/simulation/bedarf?art=produktion&id={pid}&ziel=0&datum={FREITAG}").json()
    assert r["empfehlung"] and r["empfehlung"] > 1
    assert next(p for p in r["punkte"] if p["anzahl"] == r["empfehlung"])["wartezeit"] == 0
    assert r["punkte"][0]["wartezeit"] > 0
    assert sim(haus)["produktionen"][0]["stillstand"] > 0  # nichts gespeichert
    s = c.get(f"/api/simulation/bedarf?art=stellplaetze&id={pid}&ziel=0&datum={FREITAG}").json()
    assert s["empfehlung"] > 3
    assert [p["wartezeit"] for p in s["punkte"]] == sorted((p["wartezeit"] for p in s["punkte"]), reverse=True)


def test_streuung_woche_und_excel(haus):
    c = haus["c"]
    fahrzeuge(haus, 1)
    produktion(haus, takt=2, bis="07:00", stellplaetze=3, streuung=20)
    r = c.get(f"/api/simulation/streuung?datum={FREITAG}&laeufe=10&schwelle=1").json()
    assert any(x["typ"] == "puffer" for x in r["ressourcen"])
    assert [x["name"] for x in r["lieferungen"]] == ["Küche"]
    assert c.get(f"/api/simulation/woche?von={FREITAG}").status_code == 200
    x = c.get(f"/api/export/auswertung.xlsx?datum={FREITAG}")
    blatt = load_workbook(io.BytesIO(x.content))["Produktion"]
    assert blatt["A2"].value == "Küche" and blatt["C2"].value == 16 and blatt["H2"].value > 0
