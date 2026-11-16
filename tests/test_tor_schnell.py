"""Tore an der Rampe, Lieferung in einer Zeile (automatische Transportart, Name), interne Transporte."""

import pytest

from test_planung import FREITAG, MO_FR, haus, lieferung, sim  # noqa: F401


def tor_anlegen(h, tore=1, minuten=None):
    c = h["c"]
    c.put(f"/api/knoten/{h['rampe']}", json={"art": "tor", "name": "Tor Wirtschaftshof", "kapazitaet": tore,
                                              "minuten_je_einheit": minuten or 0})


def test_lkw_belegt_tor(haus):
    tor_anlegen(haus, tore=1, minuten=3)
    wt = haus["wt"]["Palette"]["id"]
    ta = haus["ta"]["Materialtransportdienst"]["id"]
    for name in ("LKW 1", "LKW 2"):
        lieferung(haus, name=name, transportart_id=ta, rueckweg={"modus": "keiner"},
                  ladung=[{"wagentyp_id": wt, "anzahl": 2}])
    e = sim(haus)
    fahrten = {f["name"]: [] for f in e["fahrten"]}
    for f in e["fahrten"]:
        fahrten[f["name"]].append(f)
    # LKW 1: 2 Paletten × 3 min am Tor, erst danach wird geladen
    erste = min(fahrten["LKW 1"], key=lambda f: f["nr"])
    typen = [a["typ"] for a in erste["abschnitte"]]
    assert typen[:2] == ["entladen", "laden"]
    assert erste["start"] == pytest.approx(8 * 3600 + 2 * 3 * 60)
    # LKW 2 wartet, bis das einzige Tor frei ist (6 min), und braucht dann selbst 6 min
    zweite = min(fahrten["LKW 2"], key=lambda f: f["nr"])
    assert zweite["warte"]["engstelle"] == pytest.approx(6 * 60)
    assert zweite["abschnitte"][0]["typ"] == "warten"
    assert zweite["start"] == pytest.approx(8 * 3600 + 12 * 60)
    tor = next(r for r in e["ressourcen"] if r["name"] == "Tor Wirtschaftshof")
    assert tor["kapazitaet"] == 1 and {"typ": "knoten", "id": tor["id"]} in e["engpaesse"]


def test_zwei_tore_kein_warten(haus):
    tor_anlegen(haus, tore=2)
    wt = haus["wt"]["Palette"]["id"]
    for name in ("LKW 1", "LKW 2"):
        lieferung(haus, name=name, rueckweg={"modus": "keiner"}, ladung=[{"wagentyp_id": wt, "anzahl": 1}])
    e = sim(haus)
    assert all(f["warte"]["engstelle"] == 0 for f in e["fahrten"])
    assert all(f["start"] == pytest.approx(8 * 3600 + 2 * 60) for f in e["fahrten"])  # Standard: 2 min je Palette


def test_schnell_anlegen_automatisch(haus):
    c = haus["c"]
    # FTS darf den Aufzug nicht nutzen → automatisch Materialtransportdienst
    c.put(f"/api/aufzuege/{haus['aufzug']}", json={"name": "Aufzug 1", "art": "aufzug", "plaetze": 2, "fahrzeit_etage": 5, "tuerzeit": 10,
                                                    "raeumzeit": 20, "anfahrt": 15,
                                                    "transportarten": [haus["ta"]["Materialtransportdienst"]["id"]]})
    r = c.post("/api/lieferungen", json={"start_id": haus["rampe"], "ziel_id": haus["lager"], "uhrzeit": "08:00",
                                         "ladung": [{"wagentyp_id": haus["wt"]["Palette"]["id"], "anzahl": 5}],
                                         "regel": {"wochentage": MO_FR}})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["name"] == "Rampe → Wäschelager"
    assert d["transportart"] == "Materialtransportdienst" and d["weg_ok"] and d["dauer"] > 0
    l = next(x for x in c.get("/api/lieferungen").json() if x["id"] == d["id"])
    assert l["transportart_id"] == haus["ta"]["Materialtransportdienst"]["id"]


def test_schnell_ohne_weg(haus):
    c = haus["c"]
    insel = c.post("/api/knoten", json={"stockwerk_id": haus["og"], "x": 9000, "y": 9000, "art": "ziel", "name": "B25"}).json()["id"]
    r = c.post("/api/lieferungen", json={"start_id": haus["rampe"], "ziel_id": insel, "uhrzeit": "08:00", "regel": {"wochentage": MO_FR}})
    assert r.status_code == 200, r.text
    assert r.json()["weg_ok"] is False
    assert r.json()["transportart"] == "FTS"  # keine kommt durch: die erste


def test_interner_bettentransport(haus):
    """Schmutziges Bett von der Station zur Aufbereitung, sauberes Bett zurück."""
    c = haus["c"]
    bett = haus["wt"].get("Bett") or next(w for w in c.get("/api/stammdaten").json()["wagentypen"] if w["name"] == "Bett")
    lid = lieferung(haus, name="Bettentausch", richtung="intern", start_id=haus["lager"], ziel_id=haus["rampe"],
                    ladung=[{"wagentyp_id": bett["id"], "anzahl": 1}], rueckweg={"modus": "beladen"})
    e = sim(haus)
    f = next(x for x in e["fahrten"] if x["lieferung_id"] == lid)
    assert f["richtung"] == "intern"
    typen = [a["typ"] for a in f["abschnitte"]]
    assert typen.count("entladen") == 2  # an der Aufbereitung und zurück auf Station
    assert c.post("/api/lieferungen", json={"start_id": haus["rampe"], "ziel_id": haus["lager"], "uhrzeit": "08:00",
                                            "richtung": "quer"}).status_code == 400


def test_flur_loeschen_raeumt_zwischenpunkte_auf(haus):
    c = haus["c"]
    a = c.post("/api/knoten", json={"stockwerk_id": haus["ug"], "x": 0, "y": 500, "art": "weg"}).json()["id"]
    b = c.post("/api/knoten", json={"stockwerk_id": haus["ug"], "x": 500, "y": 500, "art": "weg"}).json()["id"]
    kid = c.post("/api/kanten", json={"von": a, "nach": b}).json()["id"]
    c.post("/api/kanten", json={"von": b, "nach": haus["flur"]})
    c.delete(f"/api/kanten/{kid}")
    ids = {k["id"] for k in c.get(f"/api/stockwerke/{haus['ug']}/netz").json()["knoten"]}
    assert a not in ids  # loses Ende weg
    assert b in ids  # hängt noch am Flur
    # benannte Punkte bleiben auch ohne Weg stehen
    kante = next(k for k in c.get(f"/api/stockwerke/{haus['ug']}/netz").json()["kanten"] if haus["rampe"] in (k["von"], k["nach"]))
    c.delete(f"/api/kanten/{kante['id']}")
    assert haus["rampe"] in {k["id"] for k in c.get(f"/api/stockwerke/{haus['ug']}/netz").json()["knoten"]}


def test_punkte_vereinen(haus):
    """Offenes Streckenende auf einen Punkt gezogen: beide werden einer, die Strecke hängt dran."""
    c = haus["c"]
    ende = c.post("/api/knoten", json={"stockwerk_id": haus["ug"], "x": 1000, "y": 900, "art": "weg"}).json()["id"]
    oben = c.post("/api/knoten", json={"stockwerk_id": haus["ug"], "x": 1000, "y": 1500, "art": "weg"}).json()["id"]
    c.post("/api/kanten", json={"von": oben, "nach": ende})
    r = c.post(f"/api/knoten/{ende}/vereinen", json={"mit": haus["flur"]})
    assert r.status_code == 200 and r.json()["id"] == haus["flur"]
    netz = c.get(f"/api/stockwerke/{haus['ug']}/netz").json()
    assert ende not in {k["id"] for k in netz["knoten"]}
    assert any({k["von"], k["nach"]} == {oben, haus["flur"]} for k in netz["kanten"])
    # benannter Punkt bleibt erhalten, wenn ein Streckenpunkt auf ihn gezogen wird
    assert c.post(f"/api/knoten/{oben}/vereinen", json={"mit": haus["rampe"]}).json()["id"] == haus["rampe"]
    # zwei benannte Punkte: nein
    assert c.post(f"/api/knoten/{haus['rampe']}/vereinen", json={"mit": haus["a_ug"]}).status_code == 409
    # Rückgängig stellt den Stand wieder her
    assert c.post(f"/api/stockwerke/{haus['ug']}/rueckgaengig").status_code == 200
    assert oben in {k["id"] for k in c.get(f"/api/stockwerke/{haus['ug']}/netz").json()["knoten"]}


def test_nein_bei_luecke_wird_gemerkt(haus):
    c = haus["c"]
    ende = c.post("/api/knoten", json={"stockwerk_id": haus["ug"], "x": 1000, "y": 900, "art": "weg"}).json()["id"]
    assert c.put(f"/api/knoten/{ende}", json={"ohne_hinweis": True}).status_code == 200
    k = next(k for k in c.get(f"/api/stockwerke/{haus['ug']}/netz").json()["knoten"] if k["id"] == ende)
    assert k["ohne_hinweis"] == 1


def test_pdf_mit_vorspann_wird_angenommen(admin):
    from conftest import pdf_bytes

    r = admin.post("/api/dokumente", files={"datei": ("plot.pdf", b"\r\n  " + pdf_bytes(), "application/pdf")})
    assert r.status_code == 200, r.text
    assert admin.post("/api/dokumente", files={"datei": ("x.pdf", b"kein pdf" * 10, "application/pdf")}).status_code == 400


def test_upload_in_stuecken(admin, client):
    from conftest import pdf_bytes

    daten = b"\n" + pdf_bytes() + b"%" + b"x" * 300_000
    uid = admin.post("/api/uploads").json()["id"]
    teile = [daten[i : i + 100_000] for i in range(0, len(daten), 100_000)]
    for nr, teil in enumerate(teile):
        r = admin.put(f"/api/uploads/{uid}?nr={nr}", content=teil, headers={"Content-Type": "application/octet-stream"})
        assert r.status_code == 200, r.text
    # falsche Reihenfolge wird abgelehnt
    assert admin.put(f"/api/uploads/{uid}?nr=0", content=b"x").status_code == 409
    r = admin.post(f"/api/uploads/{uid}/fertig", json={"dateiname": "EG gross.pdf"})
    assert r.status_code == 200, r.text
    dok = next(d for d in admin.get("/api/dokumente").json() if d["id"] == r.json()["id"])
    assert dok["dateiname"] == "EG gross.pdf" and dok["groesse"] == len(daten)
    # danach gibt es den Upload nicht mehr
    assert admin.post(f"/api/uploads/{uid}/fertig", json={}).status_code == 404
    # Protokoll: ein Eintrag für das Dokument, keiner je Stück
    eintraege = admin.get("/api/protokoll").json()["eintraege"]
    assert sum(1 for e in eintraege if e["objekt"] == "uploads") == 0
    assert any(e["objekt"] == "dokumente" and e["bezeichnung"] == "EG gross.pdf" for e in eintraege)
