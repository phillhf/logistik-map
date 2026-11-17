"""Streuung (viele Tage mit Zufall), Mindestbedarf, Grundlast der Aufzüge."""

import time

import pytest

from test_planung import FREITAG, haus, lieferung, sim  # noqa: F401


def tor(h, tore=1, von=None, bis=None):
    h["c"].put(f"/api/knoten/{h['rampe']}", json={"art": "tor", "name": "Tor", "kapazitaet": tore,
                                                 "minuten_je_einheit": von or 0, "minuten_je_einheit_bis": bis or 0})


def lkw(h, n=4, uhrzeit="08:00", streuung=0):
    wt = h["wt"]["Palette"]["id"]
    for i in range(n):
        lieferung(h, name=f"LKW {i + 1}", uhrzeit=uhrzeit, streuung=streuung, rueckweg={"modus": "keiner"},
                  ladung=[{"wagentyp_id": wt, "anzahl": 5}])


def test_ohne_streuung_jeder_tag_gleich(haus):
    tor(haus)
    lkw(haus, 2)
    r = haus["c"].get(f"/api/simulation/streuung?datum={FREITAG}&laeufe=10&schwelle=5").json()
    t = next(x for x in r["ressourcen"] if x["typ"] == "knoten")
    assert t["median"] == t["p90"] == t["max"] == pytest.approx(10 * 60)  # zweiter LKW wartet 5 × 2 min
    assert t["anteil_ueber"] == 1.0
    # die normale Tagesrechnung bleibt ohne Zufall
    assert sim(haus)["zusammenfassung"] == sim(haus)["zusammenfassung"]


def test_streuung_ergibt_verteilung(haus):
    tor(haus, von=1, bis=3)
    lkw(haus, 3, streuung=30)
    t0 = time.time()
    r = haus["c"].get(f"/api/simulation/streuung?datum={FREITAG}&laeufe=100&schwelle=10").json()
    dauer = time.time() - t0
    assert r["laeufe"] == 100
    t = next(x for x in r["ressourcen"] if x["typ"] == "knoten")
    assert 0 < t["anteil_ueber"] < 1  # mal staut es, mal nicht
    assert t["median"] <= t["p90"] <= t["max"]
    assert len(r["lieferungen"]) == 3
    assert dauer < 10, dauer
    # gleiche Eingabe → gleiches Ergebnis (feste Startwerte)
    assert haus["c"].get(f"/api/simulation/streuung?datum={FREITAG}&laeufe=100&schwelle=10").json()["ressourcen"] == r["ressourcen"]


def test_mindestbedarf_tore(haus):
    tor(haus, 1)
    lkw(haus, 4)  # vier LKW gleichzeitig, je 10 min am Tor
    r = haus["c"].get(f"/api/simulation/bedarf?art=knoten&id={haus['rampe']}&ziel=10&datum={FREITAG}").json()
    assert r["empfehlung"] == 2  # mit 2 Toren wartet keiner länger als 10 min
    werte = {p["anzahl"]: p["wartezeit"] for p in r["punkte"]}
    assert werte[1] == pytest.approx(1800) and werte[2] == pytest.approx(600)
    assert max(werte) == 3  # eine Stufe mehr zum Vergleich
    # mit Streuung
    r = haus["c"].get(f"/api/simulation/bedarf?art=knoten&id={haus['rampe']}&ziel=10&datum={FREITAG}&laeufe=10").json()
    assert r["empfehlung"] is not None and r["laeufe"] == 10


def test_mindestbedarf_fahrzeuge(haus):
    ta = haus["ta"]["FTS"]
    for i in range(3):
        lieferung(haus, name=f"FTS {i}", transportart_id=ta["id"])
    r = haus["c"].get(f"/api/simulation/bedarf?art=transportart&id={ta['id']}&ziel=0&datum={FREITAG}").json()
    assert r["empfehlung"] == 3  # niemand soll auf ein FTS warten: 3 gleichzeitige Fahrten
    assert haus["c"].get("/api/simulation/bedarf?art=quatsch&id=1").status_code == 400


def test_grundlast_im_aufzug(haus):
    c = haus["c"]
    auf = {"name": "Aufzug 1", "art": "aufzug", "plaetze": 2, "fahrzeit_etage": 5, "tuerzeit": 10, "raeumzeit": 20,
           "anfahrt": 15, "transportarten": []}
    lieferung(haus, rueckweg={"modus": "keiner"})
    ohne = sim(haus)
    a0 = next(r for r in ohne["ressourcen"] if r["typ"] == "aufzug")
    assert a0["personenfahrten"] == 0
    r = c.put(f"/api/aufzuege/{haus['aufzug']}", json={**auf, "grundlast": [{"von": "07:00", "bis": "10:00", "prozent": 90, "wochentage": [5]}]})
    assert r.status_code == 200, r.text
    assert c.get("/api/stammdaten").json()["aufzuege"][0]["grundlast"][0]["prozent"] == 90
    mit = sim(haus)
    a1 = next(r for r in mit["ressourcen"] if r["typ"] == "aufzug")
    assert a1["personenfahrten"] > 100 and a1["fahrten"] == 1  # Waren zählen getrennt
    assert a1["spitze"] >= 0.9
    assert mit["fahrten"][0]["warte"]["aufzug"] > 0  # die Ware wartet jetzt auf die Kabine
    assert len(next(r for r in mit["ressourcen"] if r["typ"] == "aufzug")["belegungen"][0]) == 5
    # anderer Wochentag (Freitag = 5 ist gesetzt): Samstag ohne Grundlast
    sa = c.get("/api/simulation?datum=2026-06-06").json()
    assert all(r.get("personenfahrten", 0) == 0 for r in sa["ressourcen"] if r["typ"] == "aufzug")
    # ungültige Uhrzeit
    assert c.put(f"/api/aufzuege/{haus['aufzug']}", json={**auf, "grundlast": [{"von": "7 Uhr", "bis": "10:00", "prozent": 50}]}).status_code == 400


def _warten(c, rid, grenze=30):
    ende = time.time() + grenze
    while time.time() < ende:
        r = c.get(f"/api/rechnungen/{rid}").json()
        if r["status"] != "laeuft":
            return r
        time.sleep(0.05)
    raise AssertionError("Rechnung wurde nicht fertig")


def test_rechnung_im_hintergrund(haus):
    """Streuung und Mindestbedarf laufen im Hintergrund – gleiches Ergebnis wie direkt, mit Fortschritt."""
    c = haus["c"]
    tor(haus, von=1, bis=3)
    lkw(haus, 3, streuung=30)
    direkt = c.get(f"/api/simulation/streuung?datum={FREITAG}&laeufe=50&schwelle=10").json()
    rid = c.post("/api/rechnungen", json={"art": "streuung", "parameter": {"datum": FREITAG, "laeufe": 50, "schwelle": 10}}).json()["id"]
    r = _warten(c, rid)
    assert r["status"] == "fertig" and r["fortschritt"] == 1
    assert r["ergebnis"]["ressourcen"] == direkt["ressourcen"]

    rid = c.post("/api/rechnungen", json={"art": "bedarf", "parameter": {"art": "knoten", "id": haus["rampe"], "ziel": 10, "datum": FREITAG}}).json()["id"]
    assert _warten(c, rid)["ergebnis"]["empfehlung"] is not None

    # Fehler kommen als Code zurück, fremde/unbekannte Nummern gibt es nicht
    rid = c.post("/api/rechnungen", json={"art": "bedarf", "parameter": {"art": "quatsch", "id": 1}}).json()["id"]
    r = _warten(c, rid)
    assert r["status"] == "fehler" and r["fehler"]["code"] == "art_ungueltig"
    assert c.get("/api/rechnungen/unbekannt").status_code == 404
    assert c.post("/api/rechnungen", json={"art": "quatsch"}).status_code == 422


def test_rechnung_abbrechen(haus):
    c = haus["c"]
    tor(haus, von=1, bis=3)
    lkw(haus, 3, streuung=30)
    rid = c.post("/api/rechnungen", json={"art": "streuung", "parameter": {"datum": FREITAG, "laeufe": 500}}).json()["id"]
    assert c.delete(f"/api/rechnungen/{rid}").status_code == 200
    assert _warten(c, rid)["status"] in ("abgebrochen", "fertig")
