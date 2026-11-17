"""Standorte: mehrere Krankenhäuser in einer Installation, sauber getrennt."""

from test_planung import FREITAG, haus, lieferung, sim  # noqa: F401


def test_zweites_krankenhaus_ist_getrennt(haus):
    c = haus["c"]
    lid = lieferung(haus)
    erster = c.get("/api/standorte").json()
    assert len(erster["standorte"]) == 1
    sid1 = erster["aktuell"]
    c.put("/api/einstellungen", json={"bundesland": "BY"})

    # neues Krankenhaus, Stammdaten vom ersten übernehmen und gleich dorthin wechseln
    r = c.post("/api/standorte", json={"name": "Klinik Nord", "stammdaten_von": sid1})
    assert r.status_code == 200, r.text
    sid2 = r.json()["id"]
    assert c.get("/api/standorte").json()["aktuell"] == sid2

    # dort ist alles leer – bis auf die übernommenen Transportarten und Wagentypen
    assert c.get("/api/gebaeude").json() == []
    assert c.get("/api/lieferungen").json() == []
    assert c.get("/api/punkte").json() == []
    assert c.get("/api/dokumente").json() == []
    sd = c.get("/api/stammdaten").json()
    assert {t["name"] for t in sd["transportarten"]} == {"FTS", "Materialtransportdienst"}
    assert sd["aufzuege"] == []
    assert all(t["id"] not in {x["id"] for x in haus["ta"].values()} for t in sd["transportarten"])
    # eigene „Erste Schritte“: Bundesland vorgeschlagen, aber noch nicht bestätigt
    schritte = {s["id"]: s for s in c.get("/api/einrichtung").json()["schritte"]}
    assert schritte["gebaeude"]["status"] == "offen" and schritte["bundesland"]["status"] == "offen"
    assert schritte["bundesland"]["zahlen"]["bundesland"] == "BY"
    assert c.get(f"/api/simulation?datum={FREITAG}").json()["zusammenfassung"]["fahrten"] == 0

    # etwas im neuen Haus anlegen
    gid = c.post("/api/gebaeudeteile", json={"name": "Haus N"}).json()["id"]
    assert [t["id"] for t in c.get("/api/gebaeude").json()] == [gid]

    # zurück zum ersten: alles wie vorher, nichts vom zweiten zu sehen
    assert c.post(f"/api/standorte/{sid1}/waehlen").status_code == 200
    assert gid not in [t["id"] for t in c.get("/api/gebaeude").json()]
    assert [l["id"] for l in c.get("/api/lieferungen").json()] == [lid]
    assert sim(haus)["zusammenfassung"]["fahrten"] == 1

    # umbenennen und löschen (aktueller bleibt), letzter Standort lässt sich nicht löschen
    assert c.put(f"/api/standorte/{sid2}", json={"name": "Klinik Nord-West"}).status_code == 200
    assert c.delete(f"/api/standorte/{sid2}").status_code == 200
    assert [s["id"] for s in c.get("/api/standorte").json()["standorte"]] == [sid1]
    assert c.delete(f"/api/standorte/{sid1}").status_code == 409
    assert c.get("/api/gebaeude").json()


def test_unbekannter_standort_im_cookie(haus):
    c = haus["c"]
    c.cookies.set("lm_standort", "999")
    assert c.get("/api/gebaeude").json()  # fällt auf den ersten Standort zurück
    assert c.post("/api/standorte/999/waehlen").status_code == 404


def test_neuer_standort_mit_standardwerten(admin):
    r = admin.post("/api/standorte", json={"name": "Neu", "wechseln": False})
    sid = r.json()["id"]
    admin.post(f"/api/standorte/{sid}/waehlen")
    sd = admin.get("/api/stammdaten").json()
    assert {w["name"] for w in sd["wagentypen"]} >= {"Palette", "Bett"}
    assert len(sd["transportarten"]) == 2


def test_nur_verwalter_legen_standorte_an(client, admin):
    admin.post("/api/benutzer", json={"benutzername": "plan", "anzeigename": "P", "passwort": "geheim-12345", "rolle": "planer"})
    client.post("/api/abmelden")
    client.post("/api/anmelden", json={"benutzername": "plan", "passwort": "geheim-12345"})
    assert client.post("/api/standorte", json={"name": "X"}).status_code == 403
    assert client.get("/api/standorte").status_code == 200


def test_zugriff_je_krankenhaus(haus, app):
    """Ein Benutzer, der nur Klinik Nord sehen darf, kommt an das erste Haus nicht heran – auch nicht über Nummern."""
    from fastapi.testclient import TestClient

    c = haus["c"]
    lid = lieferung(haus)
    sid1 = c.get("/api/standorte").json()["aktuell"]
    sid2 = c.post("/api/standorte", json={"name": "Klinik Nord", "wechseln": False}).json()["id"]
    r = c.post("/api/benutzer", json={"benutzername": "nord", "passwort": "geheim123", "rolle": "planer", "standorte": [sid2]})
    assert r.status_code == 200, r.text
    bid = r.json()["id"]
    assert next(b for b in c.get("/api/benutzer").json() if b["id"] == bid)["standorte"] == [sid2]

    n = TestClient(app)  # ohne „with“: sonst schließt das Ende die gemeinsame Datenbank
    assert n.post("/api/anmelden", json={"benutzername": "nord", "passwort": "geheim123"}).status_code == 200
    st = n.get("/api/standorte").json()
    assert st["aktuell"] == sid2 and [s["id"] for s in st["standorte"]] == [sid2]
    assert n.get("/api/lieferungen").json() == []
    # erstes Haus: weder wählen noch über Nummern lesen oder ändern
    assert n.post(f"/api/standorte/{sid1}/waehlen").status_code == 404
    n.cookies.set("lm_standort", str(sid1))
    assert n.get("/api/standorte").json()["aktuell"] == sid2
    assert n.get(f"/api/stockwerke/{haus['ug']}").status_code == 404
    assert n.get(f"/api/lieferungen/{lid}/weg").status_code == 404
    assert n.delete(f"/api/lieferungen/{lid}").status_code == 404
    assert n.get(f"/api/export/karte/{haus['ug']}.pdf").status_code == 404
    neu = {"name": "x", "transportart_id": haus["ta"]["FTS"]["id"], "start_id": haus["rampe"], "ziel_id": haus["lager"],
           "uhrzeit": "08:00", "richtung": "versorgung", "regel": {"wochentage": [1]}, "rueckweg": {"modus": "keiner"}}
    assert n.post("/api/lieferungen", json=neu).status_code == 404

    # Admin sieht weiter alles; ohne Zuordnung sieht der Benutzer wieder alle Häuser
    assert c.get(f"/api/lieferungen/{lid}/weg").status_code == 200
    # Haus löschen geht nicht, solange jemand nur dort zugeordnet ist
    r = c.delete(f"/api/standorte/{sid2}")
    assert r.status_code == 409 and r.json()["detail"]["namen"] == "nord"
    assert c.put(f"/api/benutzer/{bid}", json={"standorte": []}).status_code == 200
    assert c.delete(f"/api/standorte/{sid2}").status_code == 200
