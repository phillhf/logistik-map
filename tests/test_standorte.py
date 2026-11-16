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
