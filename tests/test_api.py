from fastapi.testclient import TestClient

from conftest import ADMIN, pdf_bytes
from logistikmap.plaene import KACHEL, kachelanzahl, max_zoom_fuer


def test_ersteinrichtung_nur_einmal(client):
    s = client.get("/api/status").json()
    assert s["ersteinrichtung"] is True and s["benutzer"] is None
    assert client.post("/api/ersteinrichtung", json={**ADMIN, "passwort": "kurz"}).json()["detail"]["code"] == "passwort_zu_kurz"
    assert client.post("/api/ersteinrichtung", json=ADMIN).status_code == 200
    s = client.get("/api/status").json()
    assert s["ersteinrichtung"] is False
    assert s["benutzer"]["rolle"] == "admin"
    assert set(s["benutzer"]["rechte"]) == {"ansehen", "bearbeiten", "verwalten"}
    r = client.post("/api/ersteinrichtung", json={**ADMIN, "benutzername": "zweiter"})
    assert r.status_code == 409


def test_ohne_anmeldung_gesperrt(client):
    assert client.get("/api/gebaeude").status_code == 401
    assert client.get("/api/plaene/1/kacheln/0/0/0.png").status_code == 401


def test_anmelden_abmelden_und_bremse(admin, app):
    admin.post("/api/abmelden")
    assert admin.get("/api/gebaeude").status_code == 401
    for _ in range(5):
        assert admin.post("/api/anmelden", json={"benutzername": "admin", "passwort": "falsch!!"}).status_code == 401
    assert admin.post("/api/anmelden", json={"benutzername": "admin", "passwort": ADMIN["passwort"]}).status_code == 429


def test_betrachter_darf_nur_ansehen(admin, app):
    r = admin.post("/api/benutzer", json={"benutzername": "gast", "passwort": "ansehen1", "rolle": "betrachter"})
    assert r.status_code == 200, r.text
    with TestClient(app) as gast:
        assert gast.post("/api/anmelden", json={"benutzername": "GAST", "passwort": "ansehen1"}).status_code == 200
        assert gast.get("/api/gebaeude").status_code == 200
        assert gast.post("/api/gebaeudeteile", json={"name": "X"}).json()["detail"]["code"] == "keine_berechtigung"
        assert gast.get("/api/benutzer").status_code == 403


def test_letzter_admin_bleibt(admin):
    ich = admin.get("/api/status").json()["benutzer"]
    r = admin.put(f"/api/benutzer/{ich['id']}", json={"rolle": "betrachter"})
    assert r.json()["detail"]["code"] == "letzter_admin"
    assert admin.delete(f"/api/benutzer/{ich['id']}").json()["detail"]["code"] == "sich_selbst_loeschen"


def test_deaktivierter_benutzer_fliegt_raus(admin, app):
    bid = admin.post("/api/benutzer", json={"benutzername": "weg", "passwort": "abcdefgh", "rolle": "betrachter"}).json()["id"]
    with TestClient(app) as c:
        c.post("/api/anmelden", json={"benutzername": "weg", "passwort": "abcdefgh"})
        assert c.get("/api/gebaeude").status_code == 200
        admin.put(f"/api/benutzer/{bid}", json={"aktiv": False})
        assert c.get("/api/gebaeude").status_code == 401


def test_eigenes_passwort(admin):
    r = admin.post("/api/ich/passwort", json={"altes_passwort": "falsch", "neues_passwort": "neuesPasswort"})
    assert r.json()["detail"]["code"] == "altes_passwort_falsch"
    r = admin.post("/api/ich/passwort", json={"altes_passwort": ADMIN["passwort"], "neues_passwort": "neuesPasswort"})
    assert r.status_code == 200
    assert admin.get("/api/gebaeude").status_code == 200  # aktuelle Sitzung bleibt


def test_einstellungen_und_feiertage(admin):
    e = admin.get("/api/einstellungen").json()
    assert e["bundesland"] == "NW" and "BY" in e["bundeslaender"]
    assert admin.put("/api/einstellungen", json={"bundesland": "XX"}).status_code == 400
    admin.post("/api/sondertage", json={"datum": "2026-12-24", "name": "Heiligabend (Notbetrieb)"})
    t = admin.get("/api/feiertage?jahr=2026").json()
    assert len([x for x in t["tage"] if x["art"] == "gesetzlich"]) == 11
    assert any(x.get("name") == "Heiligabend (Notbetrieb)" for x in t["tage"])
    admin.put("/api/einstellungen", json={"bundesland": "BE"})
    t = admin.get("/api/feiertage?jahr=2026").json()
    assert t["bundesland"] == "BE"
    assert "frauentag" in [x.get("schluessel") for x in t["tage"]]


def test_gebaeude_stockwerke_plan(admin, app):
    gid = admin.post("/api/gebaeudeteile", json={"name": "Haus A", "kuerzel": "A"}).json()["id"]
    sid_ug = admin.post("/api/stockwerke", json={"gebaeudeteil_id": gid, "name": "Untergeschoss", "ebene": -1}).json()["id"]
    sid_eg = admin.post("/api/stockwerke", json={"gebaeudeteil_id": gid, "name": "Erdgeschoss", "ebene": 0}).json()["id"]

    r = admin.post("/api/dokumente", files={"datei": ("plaene.pdf", pdf_bytes([(842, 595), (1190, 842)]), "application/pdf")})
    assert r.status_code == 200, r.text
    dok = r.json()
    assert [s["nr"] for s in dok["seiten"]] == [1, 2]
    assert admin.get(f"/api/dokumente/{dok['id']}/vorschau/2").headers["content-type"] == "image/png"

    pid = admin.put(f"/api/stockwerke/{sid_ug}/plan", json={"dokument_id": dok["id"], "seite": 1}).json()["plan_id"]
    admin.put(f"/api/stockwerke/{sid_eg}/plan", json={"dokument_id": dok["id"], "seite": 2})
    app.state.kacheln.warte_bis_leer()

    s = admin.get(f"/api/stockwerke/{sid_ug}").json()
    assert s["plan"]["status"] == "fertig", s
    assert s["plan"]["max_zoom"] == max_zoom_fuer(842, 595)
    ordner = app.state.kacheln.ordner(pid)
    assert (ordner / "0" / "0_0.png").is_file()
    k = admin.get(f"/api/plaene/{pid}/kacheln/{s['plan']['max_zoom']}/0/0.png")
    assert k.status_code == 200 and k.content[:4] == b"\x89PNG"

    # Reihenfolge: oberstes Stockwerk zuerst
    teile = admin.get("/api/gebaeude").json()
    assert [x["name"] for x in teile[0]["stockwerke"]] == ["Erdgeschoss", "Untergeschoss"]

    # Maßstab
    assert admin.put(f"/api/stockwerke/{sid_ug}/massstab", json={"meter_pro_punkt": 0.05}).status_code == 200
    assert admin.get(f"/api/stockwerke/{sid_ug}").json()["meter_pro_punkt"] == 0.05

    # Dokument in Verwendung kann nicht gelöscht werden
    assert admin.delete(f"/api/dokumente/{dok['id']}").status_code == 409
    admin.delete(f"/api/gebaeudeteile/{gid}")
    assert not ordner.exists()
    assert admin.delete(f"/api/dokumente/{dok['id']}").status_code == 200


def test_kein_pdf(admin):
    r = admin.post("/api/dokumente", files={"datei": ("x.pdf", b"hallo welt", "application/pdf")})
    assert r.json()["detail"]["code"] == "kein_pdf"


def test_kacheln_randkacheln_volle_groesse(tmp_path):
    import pymupdf

    from logistikmap.plaene import kacheln_erzeugen

    pdf = tmp_path / "t.pdf"
    pdf.write_bytes(pdf_bytes([(1000, 700)]))
    kacheln_erzeugen(pdf, 1, tmp_path / "k", 5)
    for p in (tmp_path / "k").rglob("*.png"):
        pix = pymupdf.Pixmap(str(p))
        assert (pix.width, pix.height) == (KACHEL, KACHEL), p
    assert kachelanzahl(1000, 700, 5) >= len(list((tmp_path / "k").rglob("*.png")))


def test_max_zoom():
    assert max_zoom_fuer(3370, 2384) == 6  # A0: Maßstab 4
    assert max_zoom_fuer(842, 595) == 7  # A4: begrenzt auf Maßstab 8
    assert max_zoom_fuer(100000, 50000) == 1  # Maßstab 1/8
    assert max_zoom_fuer(10**7, 10**7) == 0


def test_spa_fallback(client):
    assert "<html" in client.get("/").text.lower()
    assert client.get("/api/gibtsnicht").json()["detail"]["code"] == "nicht_gefunden"
