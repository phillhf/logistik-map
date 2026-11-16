"""Seite „Erste Schritte“: Prüfung, was beim Einrichten noch fehlt."""

from test_planung import haus, lieferung  # noqa: F401  (Fixture und Hilfe wiederverwenden)


def schritte(c) -> dict:
    r = c.get("/api/einrichtung")
    assert r.status_code == 200, r.text
    return {s["id"]: s for s in r.json()["schritte"]}


def codes(schritt) -> list[str]:
    return [p["code"] for p in schritt["probleme"]]


def test_leer_alles_offen(admin):
    daten = admin.get("/api/einrichtung").json()
    assert daten["erledigt"] == 0 and daten["gesamt"] == 7 and not daten["fertig"]
    s = {x["id"]: x for x in daten["schritte"]}
    assert all(s[k]["status"] == "offen" for k in ("bundesland", "gebaeude", "plaene", "karte", "stammdaten", "lieferungen"))
    assert s["ergebnis"]["status"] == "gesperrt"
    assert [o["id"] for o in daten["optional"]] == ["benutzer", "ad", "https"]


def test_bestaetigungen(admin):
    assert admin.post("/api/einrichtung/bestaetigen", json={"schritt": "unsinn"}).status_code == 400
    admin.post("/api/einrichtung/bestaetigen", json={"schritt": "stammdaten"})
    assert schritte(admin)["stammdaten"]["status"] == "hinweis"  # Materialtransportdienst ist unbegrenzt
    assert "anzahl_unbegrenzt" in codes(schritte(admin)["stammdaten"])
    # Bundesland speichern zählt als bestätigt
    admin.put("/api/einstellungen", json={"bundesland": "BY"})
    s = schritte(admin)["bundesland"]
    assert s["status"] == "erledigt" and s["zahlen"]["bundesland"] == "BY"


def test_gebaeude_und_plaene(admin):
    gid = admin.post("/api/gebaeudeteile", json={"name": "Haus B"}).json()["id"]
    assert codes(schritte(admin)["gebaeude"]) == ["teil_ohne_stockwerke"]
    admin.post("/api/stockwerke", json={"gebaeudeteil_id": gid, "name": "EG", "ebene": 0})
    s = schritte(admin)
    assert s["gebaeude"]["status"] == "erledigt"
    assert s["plaene"]["status"] == "offen" and codes(s["plaene"]) == ["kein_plan"]


def test_netz_probleme(haus):
    c = haus["c"]
    s = schritte(c)["karte"]
    assert s["status"] == "erledigt", s
    # Punkt ohne Weg und ein Aufzug, der nur auf einem Stockwerk hält
    k = c.post("/api/knoten", json={"stockwerk_id": haus["og"], "x": 5, "y": 5, "art": "ziel", "name": "Station 3"}).json()["id"]
    auf = c.post("/api/aufzuege", json={"name": "Aufzug 2", "art": "aufzug", "plaetze": 2, "fahrzeit_etage": 5, "tuerzeit": 10,
                                         "raeumzeit": 20, "anfahrt": 15, "transportarten": []}).json()["id"]
    c.post("/api/knoten", json={"stockwerk_id": haus["ug"], "x": 9, "y": 9, "art": "aufzug", "name": "A2 UG", "aufzug_id": auf})
    s = schritte(c)["karte"]
    assert s["status"] == "offen"
    assert {"punkt_ohne_weg", "aufzug_ein_halt"} <= set(codes(s))
    p = next(p for p in s["probleme"] if p["code"] == "punkt_ohne_weg" and p["werte"]["name"] == "Station 3")
    assert p["link"] == f"#/karte/{haus['og']}/bearbeiten/knoten/{k}"


def test_lieferung_ohne_verbindung(haus):
    c = haus["c"]
    # Ziel auf dem 2. OG, das nur über den Aufzug erreichbar ist – Aufzug für FTS sperren
    c.put(f"/api/aufzuege/{haus['aufzug']}", json={"name": "Aufzug 1", "art": "aufzug", "plaetze": 2, "fahrzeit_etage": 5, "tuerzeit": 10,
                                                    "raeumzeit": 20, "anfahrt": 15,
                                                    "transportarten": [haus["ta"]["Materialtransportdienst"]["id"]]})
    lid = lieferung(haus, transportart_id=haus["ta"]["FTS"]["id"])
    s = schritte(c)["lieferungen"]
    assert s["status"] == "offen"
    p = s["probleme"][0]
    assert p["code"] == "lieferung_aufzug_nicht_erlaubt" and p["werte"]["aufzuege"] == "Aufzug 1"
    assert p["link"] == "#/stammdaten" and lid
    # Aufzug wieder für alle, dafür eine Lücke im OG: Lager vom Aufzug trennen
    c.put(f"/api/aufzuege/{haus['aufzug']}", json={"name": "Aufzug 1", "art": "aufzug", "plaetze": 2, "fahrzeit_etage": 5, "tuerzeit": 10,
                                                    "raeumzeit": 20, "anfahrt": 15, "transportarten": []})
    assert schritte(c)["lieferungen"]["status"] == "erledigt"
    netz = c.get(f"/api/stockwerke/{haus['og']}/netz").json()
    for k in netz["kanten"]:
        c.delete(f"/api/kanten/{k['id']}")
    s = schritte(c)
    p = s["lieferungen"]["probleme"][0]
    assert p["code"] == "lieferung_keine_verbindung"
    assert p["werte"]["ziel_stockwerk"] == "2. OG" and "UG" in p["werte"]["erreichbar"]
    assert p["link"] == f"#/karte/{haus['og']}/bearbeiten"
    assert "punkt_ohne_weg" in codes(s["karte"])


def test_nur_mit_bearbeiten_recht(client, admin):
    admin.post("/api/benutzer", json={"benutzername": "leser", "anzeigename": "Leser", "passwort": "geheim-12345", "rolle": "betrachter"})
    client.post("/api/abmelden")
    client.post("/api/anmelden", json={"benutzername": "leser", "passwort": "geheim-12345"})
    assert client.get("/api/einrichtung").status_code == 403


def test_alle_hinweise_haben_texte():
    """Jeder Code aus einrichtung.py steht in de.json unter start.problem."""
    import json
    import re
    from pathlib import Path

    wurzel = Path(__file__).resolve().parent.parent / "logistikmap"
    quelle = (wurzel / "einrichtung.py").read_text(encoding="utf-8") + (wurzel / "netz.py").read_text(encoding="utf-8")
    codes = set(re.findall(r'_problem\(\s*"(\w+)"', quelle))
    codes |= {"lieferung_" + c for c in re.findall(r'return \{"code": "(\w+)"', quelle)}
    de = json.loads((wurzel / "static" / "i18n" / "de.json").read_text(encoding="utf-8"))
    assert len(codes) > 15
    assert not codes - set(de["start"]["problem"]), codes - set(de["start"]["problem"])
    schritte = set(re.findall(r'_schritt\(\s*"(\w+)"', quelle)) | {"ergebnis"}
    assert not schritte - set(de["start"]["schritt"])
