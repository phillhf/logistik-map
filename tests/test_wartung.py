"""Sicherung, Updates, Protokoll, Rollen, Verzeichnis-Anmeldung, HTTPS, Plan-Test."""

import io
from contextlib import nullcontext
import zipfile

import pytest
from fastapi.testclient import TestClient

from conftest import ADMIN, pdf_bytes
from logistikmap import wartung
from logistikmap.plaene import kacheln_erzeugen, plan_test


# --------------------------------------------------------------------------- Sicherung
def test_sicherung_und_wiederherstellung(admin, app):
    gid = admin.post("/api/gebaeudeteile", json={"name": "Haus A"}).json()["id"]
    admin.post("/api/dokumente", files={"datei": ("p.pdf", pdf_bytes(), "application/pdf")})
    r = admin.get("/api/sicherung")
    assert r.status_code == 200 and r.headers["content-type"] == "application/zip"
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        namen = z.namelist()
    assert "logistikmap.db" in namen and "manifest.json" in namen and any(n.startswith("dokumente/") for n in namen)
    sicherung = r.content

    # Änderungen nach der Sicherung …
    admin.delete(f"/api/gebaeudeteile/{gid}")
    admin.post("/api/gebaeudeteile", json={"name": "Neu"})
    # … werden durch die Wiederherstellung verworfen
    r = admin.post("/api/sicherung/wiederherstellen", files={"datei": ("s.zip", sicherung, "application/zip")})
    assert r.status_code == 200, r.text
    assert [t["name"] for t in admin.get("/api/gebaeude").json()] == ["Haus A"]
    assert len(admin.get("/api/dokumente").json()) == 1
    # vorher wurde automatisch gesichert
    assert any(s["name"].startswith("vor-wiederherstellung") for s in admin.get("/api/sicherungen").json())


def test_kaputte_sicherung(admin):
    r = admin.post("/api/sicherung/wiederherstellen", files={"datei": ("x.zip", b"kein zip", "application/zip")})
    assert r.json()["detail"]["code"] == "sicherung_ungueltig"


def test_auto_sicherung_behaelt_anzahl(app, pfade):
    db = app.state.db
    db.setze_einstellung("sicherung_anzahl", 2)
    auto = wartung.AutoSicherung(db, pfade)
    assert auto.jetzt_falls_faellig() is not None
    assert auto.jetzt_falls_faellig() is None  # heute schon gesichert
    for i in range(3):
        (pfade.sicherungen / f"auto-2000010{i}-000000.zip").write_bytes(b"x")
    import os
    import time

    for p in pfade.sicherungen.glob("auto-*.zip"):
        os.utime(p, (time.time() - 30 * 3600, time.time() - 30 * 3600))
    auto.jetzt_falls_faellig()
    assert len(list(pfade.sicherungen.glob("auto-*.zip"))) == 2


def test_nur_admin_darf_sichern(admin, app):
    admin.post("/api/benutzer", json={"benutzername": "planer", "passwort": "planer123", "rolle": "planer"})
    with nullcontext(TestClient(app)) as c:
        c.post("/api/anmelden", json={"benutzername": "planer", "passwort": "planer123"})
        assert c.get("/api/sicherung").status_code == 403


# --------------------------------------------------------------------------- Update
def test_update_pruefen():
    rel = {
        "tag_name": "v9.9.9", "body": "Neu", "html_url": "https://github.com/x",
        "assets": [
            {"name": "LogistikMap-Setup-9.9.9.exe", "browser_download_url": "https://example/LogistikMap-Setup-9.9.9.exe"},
            {"name": "LogistikMap-Setup-9.9.9.exe.sha256", "browser_download_url": "https://example/sha"},
        ],
    }
    info = wartung.update_pruefen(neu=True, abrufen=lambda url: rel)
    assert info["verfuegbar"] and info["neueste"] == "9.9.9" and info["setup_url"].endswith(".exe")
    alt = wartung.update_pruefen(neu=True, abrufen=lambda url: {**rel, "tag_name": "v0.0.1"})
    assert not alt["verfuegbar"]

    def kaputt(url):
        raise OSError("offline")

    assert wartung.update_pruefen(neu=True, abrufen=kaputt)["fehler"] == "keine_verbindung"
    assert wartung.version_tupel("1.10.0") > wartung.version_tupel("1.9.3")


# --------------------------------------------------------------------------- Protokoll & Rollen
def test_protokoll(admin):
    lid_gid = admin.post("/api/gebaeudeteile", json={"name": "Haus Protokoll"}).json()["id"]
    admin.put(f"/api/gebaeudeteile/{lid_gid}", json={"name": "Haus P"})
    admin.delete(f"/api/gebaeudeteile/{lid_gid}")
    p = admin.get("/api/protokoll").json()
    eintraege = [(e["aktion"], e["objekt"], e["bezeichnung"]) for e in p["eintraege"][:3]]
    assert eintraege == [("geloescht", "gebaeudeteile", "Haus P"), ("geaendert", "gebaeudeteile", "Haus P"), ("angelegt", "gebaeudeteile", "Haus Protokoll")]
    assert p["benutzer"] == ["admin"]
    # fehlgeschlagene Anfragen werden nicht protokolliert
    admin.delete("/api/benutzer/1")
    assert admin.get("/api/protokoll").json()["gesamt"] == p["gesamt"]


def test_rollen_verwalten(admin, app):
    r = admin.post("/api/rollen", json={"name": "Stationsleitung", "rechte": ["lieferungen"]})
    assert r.status_code == 200
    rid, schluessel = r.json()["id"], r.json()["schluessel"]
    rollen = {x["schluessel"]: x for x in admin.get("/api/rollen").json()["rollen"]}
    assert rollen[schluessel]["rechte"] == ["ansehen", "lieferungen"]
    assert rollen["admin"]["system"]
    assert admin.put(f"/api/rollen/{rollen['admin']['id']}", json={"name": "x", "rechte": []}).json()["detail"]["code"] == "systemrolle"
    admin.post("/api/benutzer", json={"benutzername": "sl", "passwort": "geheim123", "rolle": schluessel})
    assert admin.delete(f"/api/rollen/{rid}").json()["detail"]["code"] == "rolle_in_verwendung"
    with nullcontext(TestClient(app)) as c:
        c.post("/api/anmelden", json={"benutzername": "sl", "passwort": "geheim123"})
        assert c.post("/api/gebaeudeteile", json={"name": "x"}).status_code == 403  # kein „bearbeiten“
        assert c.get("/api/lieferungen").status_code == 200
    assert admin.post("/api/rollen", json={"name": "x", "rechte": ["fliegen"]}).status_code == 400


def test_sprache_je_benutzer(admin):
    assert admin.put("/api/ich", json={"sprache": "en"}).status_code == 200
    assert admin.get("/api/status").json()["sprache"] == "en"
    assert admin.put("/api/ich", json={"sprache": "fr"}).status_code == 400


# --------------------------------------------------------------------------- Verzeichnis (LDAP mit Testserver)
@pytest.fixture
def ldap_server():
    import ldap3

    server = ldap3.Server("fake_ad")
    basis = ldap3.Connection(server, user="cn=admin", password="x", client_strategy=ldap3.MOCK_SYNC)
    basis.strategy.add_entry("cn=admin", {"userPassword": "x", "sn": "admin"})
    basis.strategy.add_entry("CN=Erika Muster,OU=User,DC=klinik,DC=local", {
        "userPrincipalName": "emuster@klinik.local", "sAMAccountName": "emuster", "displayName": "Erika Muster",
        "userPassword": "Sommer2026!", "objectClass": "person",
        "memberOf": ["CN=Logistik-Planung,OU=Gruppen,DC=klinik,DC=local", "CN=Alle,OU=Gruppen,DC=klinik,DC=local"],
    })
    basis.strategy.add_entry("CN=Max Fremd,OU=User,DC=klinik,DC=local", {
        "userPrincipalName": "mfremd@klinik.local", "sAMAccountName": "mfremd", "displayName": "Max Fremd",
        "userPassword": "Winter2026!", "objectClass": "person", "memberOf": ["CN=Alle,OU=Gruppen,DC=klinik,DC=local"],
    })
    upn_zu_dn = {"emuster@klinik.local": "CN=Erika Muster,OU=User,DC=klinik,DC=local", "mfremd@klinik.local": "CN=Max Fremd,OU=User,DC=klinik,DC=local"}

    def verbinden(srv, upn, passwort):
        from logistikmap.verzeichnis import VerzeichnisFehler

        con = ldap3.Connection(server, user=upn_zu_dn.get(upn, upn), password=passwort, client_strategy=ldap3.MOCK_SYNC)
        con.strategy.entries_from_json = None
        con.strategy.connection.server.dit = basis.server.dit if hasattr(basis.server, "dit") else None
        if not con.bind():
            raise VerzeichnisFehler("anmeldung_falsch")
        return con

    return verbinden


def test_anmeldung_ueber_verzeichnis(admin, app, ldap_server):
    app.state.ldap_verbindung = ldap_server
    r = admin.put("/api/einstellungen/ldap", json={
        "aktiv": True, "server": "ldaps://dc01", "domaene": "klinik.local", "basis_dn": "DC=klinik,DC=local",
        "gruppen": [{"gruppe": "Logistik-Planung", "rolle": "planer"}], "standard_rolle": "",
    })
    assert r.status_code == 200, r.text
    test = admin.post("/api/einstellungen/ldap/test", json={"benutzername": "emuster", "passwort": "Sommer2026!"}).json()
    assert test["rolle"] == "planer" and test["anzeigename"] == "Erika Muster"
    with nullcontext(TestClient(app)) as c:
        assert c.post("/api/anmelden", json={"benutzername": "emuster", "passwort": "falsch"}).status_code == 401
        assert c.post("/api/anmelden", json={"benutzername": "emuster", "passwort": "Sommer2026!"}).status_code == 200
        ich = c.get("/api/status").json()["benutzer"]
        assert ich["anzeigename"] == "Erika Muster" and ich["rolle"] == "planer"
        assert c.post("/api/ich/passwort", json={"altes_passwort": "x", "neues_passwort": "yyyyyyyy"}).json()["detail"]["code"] == "passwort_im_verzeichnis"
    with nullcontext(TestClient(app)) as c:
        r = c.post("/api/anmelden", json={"benutzername": "mfremd", "passwort": "Winter2026!"})
        assert r.json()["detail"]["code"] == "kein_zugang_verzeichnis"
    benutzer = {b["benutzername"]: b for b in admin.get("/api/benutzer").json()}
    assert benutzer["emuster"]["quelle"] == "ldap"
    # lokaler Admin funktioniert weiter
    with nullcontext(TestClient(app)) as c:
        assert c.post("/api/anmelden", json={"benutzername": "admin", "passwort": ADMIN["passwort"]}).status_code == 200


def test_rolle_fuer_gruppen():
    from logistikmap.verzeichnis import rolle_fuer

    e = {"gruppen": [{"gruppe": "CN=Admins,OU=G,DC=x", "rolle": "admin"}, {"gruppe": "Planer", "rolle": "planer"}], "standard_rolle": "betrachter"}
    assert rolle_fuer(e, ["CN=Planer,OU=G,DC=x"]) == "planer"
    assert rolle_fuer(e, ["CN=Admins,OU=G,DC=x", "CN=Planer,OU=G,DC=x"]) == "admin"
    assert rolle_fuer(e, []) == "betrachter"


# --------------------------------------------------------------------------- HTTPS
def test_https_einstellung(admin, tmp_path):
    assert admin.put("/api/einstellungen/https", json={"zertifikat": "a.pem", "schluessel": ""}).json()["detail"]["code"] == "https_beide_dateien"
    assert admin.put("/api/einstellungen/https", json={"zertifikat": str(tmp_path / "x.pem"), "schluessel": str(tmp_path / "y.pem")}).json()["detail"]["code"] == "datei_fehlt"
    (tmp_path / "x.pem").write_text("kein zertifikat")
    (tmp_path / "y.pem").write_text("kein schlüssel")
    assert admin.put("/api/einstellungen/https", json={"zertifikat": str(tmp_path / "x.pem"), "schluessel": str(tmp_path / "y.pem")}).json()["detail"]["code"] == "zertifikat_ungueltig"
    assert admin.put("/api/einstellungen/https", json={"zertifikat": "", "schluessel": ""}).status_code == 200
    assert admin.get("/api/einstellungen/https").json()["aktiv"] is False


# --------------------------------------------------------------------------- Pläne
def test_parallele_kacheln_gleich_wie_seriell(tmp_path):
    pdf = tmp_path / "t.pdf"
    pdf.write_bytes(pdf_bytes([(1190, 842)]))
    kacheln_erzeugen(pdf, 1, tmp_path / "seriell", 5, prozesse=1)
    kacheln_erzeugen(pdf, 1, tmp_path / "parallel", 5, prozesse=2)
    a = sorted(p.relative_to(tmp_path / "seriell").as_posix() for p in (tmp_path / "seriell").rglob("*.png"))
    b = sorted(p.relative_to(tmp_path / "parallel").as_posix() for p in (tmp_path / "parallel").rglob("*.png"))
    assert a == b and len(a) > 20


def test_plan_test(tmp_path):
    pdf = tmp_path / "t.pdf"
    pdf.write_bytes(pdf_bytes([(3370, 2384)]))
    e = plan_test(pdf)
    assert e["seiten"][0]["breite_mm"] == 1189 and e["seiten"][0]["max_zoom"] == 6
    assert e["seiten"][0]["geschaetzt_s"] >= 0
