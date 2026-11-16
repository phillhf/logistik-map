"""Korrekturen aus der Durchsicht nach 0.3.0: Rückgängig, Sitzungen, Anmeldesperre, Aufzug, Mitternacht."""

from contextlib import nullcontext

import pytest
from fastapi.testclient import TestClient

from logistikmap.auth import Anmeldebremse
from test_planung import FREITAG, haus, lieferung, sim  # noqa: F401


# --------------------------------------------------------------------------- Rückgängig
def test_rueckgaengig_gruppe_ist_ein_schritt(haus):
    c, ug = haus["c"], haus["ug"]
    vorher = len(c.get(f"/api/stockwerke/{ug}/netz").json()["kanten"])
    schritte = len(c.get(f"/api/stockwerke/{ug}/verlauf").json())
    kopf = {"X-Rueckgaengig-Gruppe": "klick-1"}
    netz = c.get(f"/api/stockwerke/{ug}/netz").json()
    kante = next(k for k in netz["kanten"] if {k["von"], k["nach"]} == {haus["rampe"], haus["flur"]})
    neu = c.post(f"/api/kanten/{kante['id']}/teilen", json={"x": 500, "y": 0}, headers=kopf).json()["id"]
    p = c.post("/api/knoten", json={"stockwerk_id": ug, "x": 500, "y": 300}, headers=kopf).json()["id"]
    c.post("/api/kanten", json={"von": neu, "nach": p}, headers=kopf)
    assert len(c.get(f"/api/stockwerke/{ug}/verlauf").json()) == schritte + 1
    assert c.post(f"/api/stockwerke/{ug}/rueckgaengig").status_code == 200
    assert len(c.get(f"/api/stockwerke/{ug}/netz").json()["kanten"]) == vorher


def test_abgelehnte_aenderung_kein_schritt(haus):
    c = haus["c"]
    vorher = len(c.get(f"/api/stockwerke/{haus['ug']}/verlauf").json())
    assert c.put(f"/api/knoten/{haus['flur']}", json={"art": "unsinn"}).status_code == 400
    assert len(c.get(f"/api/stockwerke/{haus['ug']}/verlauf").json()) == vorher


def test_rueckgaengig_laesst_massstab(haus):
    c, ug = haus["c"], haus["ug"]
    c.post("/api/knoten", json={"stockwerk_id": ug, "x": 1, "y": 1})
    c.put(f"/api/stockwerke/{ug}/massstab", json={"meter_pro_punkt": 0.02})
    c.post(f"/api/stockwerke/{ug}/rueckgaengig")
    assert c.get(f"/api/stockwerke/{ug}").json()["meter_pro_punkt"] == 0.02


def test_rueckgaengig_nicht_fuer_andere(haus, app):
    c, ug = haus["c"], haus["ug"]
    c.post("/api/benutzer", json={"benutzername": "zweite", "passwort": "zweite123", "rolle": "admin"})
    with nullcontext(TestClient(app)) as z:
        z.post("/api/anmelden", json={"benutzername": "zweite", "passwort": "zweite123"})
        z.post("/api/knoten", json={"stockwerk_id": ug, "x": 5, "y": 5})
        stand = c.get(f"/api/stockwerke/{ug}/stand").json()
        assert stand["benutzer"] == "zweite"
    r = c.post(f"/api/stockwerke/{ug}/rueckgaengig")
    assert r.status_code == 409 and r.json()["detail"] == {"code": "rueckgaengig_fremd", "benutzer": "zweite"}


# --------------------------------------------------------------------------- Sitzungen & Anmeldesperre
def test_sitzung_laeuft_nach_inaktivitaet_ab(admin, app):
    db = app.state.db
    admin.put("/api/einstellungen", json={"sitzung_inaktiv_stunden": 1})
    assert admin.get("/api/gebaeude").status_code == 200
    db.ausfuehren("UPDATE sitzungen SET zuletzt = datetime('now', '-2 hours')")
    assert admin.get("/api/gebaeude").status_code == 401


def test_ad_sitzung_endet_nach_hoechstdauer(admin, app):
    db = app.state.db
    db.ausfuehren("UPDATE benutzer SET quelle = 'ldap' WHERE benutzername = 'admin'")
    db.ausfuehren("UPDATE sitzungen SET erstellt = datetime('now', '-13 hours')")
    assert admin.get("/api/gebaeude").status_code == 401


def test_sperre_je_adresse_grosszuegiger():
    b = Anmeldebremse()
    for i in range(5):
        b.fehlschlag(f"u:person{i}", "a:10.0.0.5")
    assert b.gesperrt("u:person9", "a:10.0.0.5") is False  # andere am selben Terminalserver
    assert b.gesperrt("u:person0", "a:10.0.0.5") is False  # 1 Fehlversuch für diesen Namen
    for _ in range(4):
        b.fehlschlag("u:person0", "a:10.0.0.5")
    assert b.gesperrt("u:person0", "a:10.0.0.5") is True
    for i in range(30):
        b.fehlschlag(f"u:x{i}", "a:10.0.0.6")
    assert b.gesperrt("u:neu", "a:10.0.0.6") is True


# --------------------------------------------------------------------------- Simulation
def test_aufzug_ohne_wartezeit_wenn_kabine_da(haus):
    """A fährt hoch; B wartet oben und steigt direkt in die gerade angekommene Kabine – ohne Wartezeit auf die Kabine."""
    lieferung(haus, name="A", rueckweg={"modus": "keiner"})  # UG → OG: Aufzug ab 150 s, oben bei 200 s
    lieferung(haus, name="B", start_id=haus["lager"], ziel_id=haus["rampe"], rueckweg={"modus": "keiner"})  # wartet ab 140 s oben
    e = sim(haus)
    aufzug = next(r for r in e["ressourcen"] if r["typ"] == "aufzug")
    dauern = [round(b - a) for a, b, *_ in aufzug["belegungen"]]
    assert dauern == [50, 35]  # 15 + 2·10 + 3·5, danach ohne die 15 s Wartezeit auf die Kabine


def test_lieferung_ueber_mitternacht(haus):
    lieferung(haus, uhrzeit="23:50", regel={"wochentage": [1, 2, 3, 4, 5, 6, 7], "feiertage": "auch"},
              ladung=[{"wagentyp_id": haus["wt"]["Wäschewagen"]["id"], "anzahl": 10}])
    e = sim(haus, "2026-06-06")
    vortag = [f for f in e["fahrten"] if f["vortag"]]
    heute = [f for f in e["fahrten"] if not f["vortag"]]
    assert vortag, "Fahrten vom Vortag, die nach Mitternacht noch laufen, fehlen"
    assert all(f["ende"] > 0 for f in vortag)
    assert e["zusammenfassung"]["fahrten"] == len(heute) == 10
    # Auslastung nur ab Mitternacht
    aufzug = next(r for r in e["ressourcen"] if r["typ"] == "aufzug")
    assert all(s >= 0 for s, _ in aufzug["raster"])


def test_engstellen_und_punkte_mit_kapazitaet(haus):
    c = haus["c"]
    c.put(f"/api/knoten/{haus['rampe']}", json={"kapazitaet": 2})
    netz = c.get(f"/api/stockwerke/{haus['ug']}/netz").json()
    kante = netz["kanten"][0]
    c.put(f"/api/kanten/{kante['id']}", json={"name": "Brandschutztür"})
    assert [e["name"] for e in c.get("/api/engstellen").json()] == ["Brandschutztür"]
    rampe = next(p for p in c.get("/api/punkte").json() if p["id"] == haus["rampe"])
    assert rampe["kapazitaet"] == 2
    # Szenario: Wegstück gesperrt → kein Weg
    sz = c.post("/api/szenarien", json={"name": "Tür zu", "aenderungen": {"kanten": {str(kante["id"]): {"gesperrt": True}}}}).json()["id"]
    lieferung(haus)
    e = c.get(f"/api/simulation?datum={FREITAG}&szenario={sz}").json()
    assert e["fehler"] and e["fehler"][0]["code"] == "kein_weg"
