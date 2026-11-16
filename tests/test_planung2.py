"""Schichten, Szenarien, Wochenansicht, Rückgängig, Ausrichten, Import/Export, Karten-PDF."""

import io

import pymupdf
import pytest
from openpyxl import Workbook, load_workbook

from conftest import pdf_bytes
from logistikmap.planung import transformation
from logistikmap.simulation import schicht_verlauf
from test_planung import FREITAG, haus, lieferung, sim  # noqa: F401  (Fixture wird mitgenutzt)


# --------------------------------------------------------------------------- Schichten
def test_schicht_verlauf():
    schichten = [{"von": "06:00", "bis": "14:00", "anzahl": 3}, {"von": "14:00", "bis": "22:00", "anzahl": 1},
                 {"von": "22:00", "bis": "06:00", "anzahl": 1, "wochentage": [1, 2, 3, 4, 5]}]
    v = schicht_verlauf(schichten, 5)  # Freitag: Nachtschicht Do→Fr läuft bis 6 Uhr
    assert v[0] == (0.0, 1)
    assert (6 * 3600, 3) in v and (14 * 3600, 1) in v
    v_sa = schicht_verlauf(schichten, 6)  # Samstag: Nachtschicht Fr→Sa noch bis 6 Uhr, danach keine
    assert v_sa[0] == (0.0, 1) and (22 * 3600, 0) in v_sa


def test_schichten_in_simulation(haus):
    c = haus["c"]
    mtd = c.get("/api/stammdaten").json()["transportarten"][1]
    r = c.put(f"/api/transportarten/{mtd['id']}", json={**mtd, "schichten": [{"von": "08:30", "bis": "12:00", "anzahl": 1, "wochentage": []}]})
    assert r.status_code == 200, r.text
    assert c.get("/api/stammdaten").json()["transportarten"][1]["schichten"][0]["von"] == "08:30"
    lieferung(haus, rueckweg={"modus": "keiner"})
    f = sim(haus)["fahrten"][0]
    assert f["start"] == pytest.approx(8.5 * 3600)  # wartet auf Schichtbeginn
    assert f["warte"]["fahrzeug"] == pytest.approx(1800)
    bad = c.put(f"/api/transportarten/{mtd['id']}", json={**mtd, "schichten": [{"von": "8", "bis": "12:00", "anzahl": 1}]})
    assert bad.json()["detail"]["code"] == "uhrzeit_ungueltig"


# --------------------------------------------------------------------------- Szenarien
def test_szenario_und_vergleich(haus):
    c = haus["c"]
    lid = lieferung(haus, ladung=[{"wagentyp_id": haus["wt"]["Wäschewagen"]["id"], "anzahl": 6}], rueckweg={"modus": "keiner"})
    ist = sim(haus)
    aufzug = next(r for r in ist["ressourcen"] if r["typ"] == "aufzug")
    assert aufzug["max_wartezeit"] > 0
    # Was wäre, wenn der Aufzug 6 Plätze hätte?
    sz = c.post("/api/szenarien", json={"name": "Großer Aufzug", "aenderungen": {"aufzuege": {str(haus["aufzug"]): {"plaetze": 6}}}}).json()["id"]
    e = c.get(f"/api/simulation?datum={FREITAG}&szenario={sz}").json()
    assert next(r for r in e["ressourcen"] if r["typ"] == "aufzug")["max_wartezeit"] == 0
    # Aufzug außer Betrieb → kein Weg
    c.put(f"/api/szenarien/{sz}", json={"name": "Wartung", "aenderungen": {"aufzuege": {str(haus["aufzug"]): {"ausser_betrieb": True}}}})
    e = c.get(f"/api/simulation?datum={FREITAG}&szenario={sz}").json()
    assert e["fehler"] and e["fehler"][0]["code"] == "kein_weg"
    # Lieferung verschieben und übernehmen
    c.put(f"/api/szenarien/{sz}", json={"name": "Später", "aenderungen": {"lieferungen": {str(lid): {"uhrzeit": "09:30"}}}})
    e = c.get(f"/api/simulation?datum={FREITAG}&szenario={sz}").json()
    assert e["fahrten"][0]["geplant"] == 9.5 * 3600
    assert sim(haus)["fahrten"][0]["geplant"] == 8 * 3600  # Ist bleibt unverändert
    assert c.post(f"/api/szenarien/{sz}/uebernehmen").json()["lieferungen"] == 1
    assert sim(haus)["fahrten"][0]["geplant"] == 9.5 * 3600
    assert c.post("/api/szenarien", json={"name": "x", "aenderungen": {"unsinn": {}}}).status_code == 400


def test_woche(haus):
    lieferung(haus)
    w = haus["c"].get("/api/simulation/woche?von=2026-06-01").json()
    assert len(w["tage"]) == 7
    fahrten = [t["zusammenfassung"]["fahrten"] for t in w["tage"]]
    assert fahrten == [1, 1, 1, 0, 1, 0, 0]  # Do = Fronleichnam, Sa/So frei
    assert w["tage"][0]["stunden"]["8"]["fahrten"] == 1


# --------------------------------------------------------------------------- Rückgängig & Ausrichten
def test_rueckgaengig(haus):
    c, ug = haus["c"], haus["ug"]
    vorher = c.get(f"/api/stockwerke/{ug}/netz").json()
    neu = c.post("/api/knoten", json={"stockwerk_id": ug, "x": 500, "y": 500, "art": "ziel", "name": "Neu"}).json()["id"]
    c.post("/api/kanten", json={"von": neu, "nach": haus["flur"]})
    c.put(f"/api/knoten/{haus['flur']}", json={"x": 1100, "y": 0})
    assert len(c.get(f"/api/stockwerke/{ug}/verlauf").json()) >= 3
    for _ in range(3):
        assert c.post(f"/api/stockwerke/{ug}/rueckgaengig").status_code == 200
    nachher = c.get(f"/api/stockwerke/{ug}/netz").json()
    assert sorted((k["id"], k["x"], k["y"]) for k in nachher["knoten"]) == sorted((k["id"], k["x"], k["y"]) for k in vorher["knoten"])
    assert len(nachher["kanten"]) == len(vorher["kanten"])


def test_rueckgaengig_mit_lieferung(haus):
    """Ein gelöschter Wegpunkt kommt mit gleicher ID zurück – Lieferungen bleiben gültig."""
    c, ug = haus["c"], haus["ug"]
    lid = lieferung(haus)
    c.delete(f"/api/knoten/{haus['flur']}")
    assert c.get(f"/api/lieferungen/{lid}/weg").status_code == 422
    assert c.post(f"/api/stockwerke/{ug}/rueckgaengig").status_code == 200
    assert c.get(f"/api/lieferungen/{lid}/weg").status_code == 200


def test_transformation():
    # verschoben um (10, 20), gedreht um 90°, Maßstab 2
    paare = [(0, 0, 10, 20), (1, 0, 10, 22), (0, 1, 8, 20)]
    a, b, c, d, e, f = transformation(paare)
    assert (a, b, c, d, e, f) == pytest.approx((0, -2, 10, 2, 0, 20))
    a2 = transformation(paare[:2])
    assert a2 == pytest.approx((0, -2, 10, 2, 0, 20))
    with pytest.raises(ValueError):
        transformation([(0, 0, 0, 0), (1, 1, 1, 1), (2, 2, 2, 2)])


def test_ausrichten(haus):
    c, ug = haus["c"], haus["ug"]
    # neuer Plan doppelt so groß und um (100, 50) verschoben
    r = c.post(f"/api/stockwerke/{ug}/ausrichten", json={"paare": [
        {"alt_x": 0, "alt_y": 0, "neu_x": 100, "neu_y": 50}, {"alt_x": 1000, "alt_y": 0, "neu_x": 2100, "neu_y": 50}]})
    assert r.json()["massstab"] == pytest.approx(2)
    netz = c.get(f"/api/stockwerke/{ug}/netz").json()
    flur = next(k for k in netz["knoten"] if k["id"] == haus["flur"])
    assert (flur["x"], flur["y"]) == pytest.approx((2100, 50))
    assert c.get(f"/api/stockwerke/{ug}").json()["meter_pro_punkt"] == pytest.approx(0.025)
    lid = lieferung(haus)
    assert c.get(f"/api/lieferungen/{lid}/weg").json()["laenge_m"] == pytest.approx(110)  # Meter bleiben gleich


# --------------------------------------------------------------------------- Import & Export
def test_export_und_import_rundweg(haus):
    c = haus["c"]
    lieferung(haus, ladung=[{"wagentyp_id": haus["wt"]["Wäschewagen"]["id"], "anzahl": 3}], rueckweg={"modus": "spaeter", "uhrzeit": "13:30"})
    r = c.get("/api/export/lieferungen.xlsx")
    assert r.status_code == 200
    wb = load_workbook(io.BytesIO(r.content))
    ws = wb["Lieferungen"]
    zeile = [x.value for x in ws[2]]
    assert zeile[1:12] == ["Wäsche", "Wäscherei", "Versorgung", "Materialtransportdienst", "Rampe", "Wäschelager", "08:00", None, 0, "3 Wäschewagen", "Mo-Fr"]
    # Uhrzeit ändern und eine neue Zeile ohne ID ergänzen
    ws.cell(2, 8).value = "07:45"
    ws.append([None, "Apotheke", "Apotheke", "Versorgung", "FTS", "Rampe", "Wäschelager", "10:00", "", 10, "2 Rollcontainer", "Mo, Mi, Fr", "nicht", "", "", "leer", "", "", "ja", ""])
    ws.append([None, "Kaputt", "", "", "Rakete", "Mond", "Wäschelager", "25:00", "", "viel", "3 Einhörner", "Funtag", "", "", "", "", "", "", "", ""])
    puffer = io.BytesIO()
    wb.save(puffer)
    datei = {"datei": ("l.xlsx", puffer.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    pruef = c.post("/api/import/lieferungen?pruefen=true", files=datei).json()
    assert [z["fehler"] for z in pruef["zeilen"]][:2] == [[], []]
    assert set(pruef["zeilen"][2]["fehler"]) >= {"transportart_unbekannt", "start_unbekannt", "uhrzeit_ungueltig", "ladung_ungueltig", "tage_ungueltig"}
    # mit Fehlern wird nichts übernommen
    assert c.post("/api/import/lieferungen?pruefen=false", files=datei).json()["uebernommen"] is False
    assert len(c.get("/api/lieferungen").json()) == 1
    # fehlerhafte Zeile entfernen → übernehmen
    ws.delete_rows(4)
    puffer = io.BytesIO()
    wb.save(puffer)
    r = c.post("/api/import/lieferungen?pruefen=false", files={"datei": ("l.xlsx", puffer.getvalue(), "application/octet-stream")}).json()
    assert [z["aktion"] for z in r["zeilen"]] == ["geaendert", "neu"]
    alle = {l["name"]: l for l in c.get("/api/lieferungen").json()}
    assert alle["Wäsche"]["uhrzeit"] == "07:45" and alle["Wäsche"]["rueckweg"]["modus"] == "spaeter"
    assert alle["Apotheke"]["regel"]["wochentage"] == [1, 3, 5]


def test_import_csv(haus):
    csv = ("Bezeichnung;Transportart;Start;Ziel;Uhrzeit;Ladung;Tage\n"
           "Post;Materialtransportdienst;Rampe;Wäschelager;8:05;2 Rollcontainer;Mo-Fr\n").encode("cp1252")
    r = haus["c"].post("/api/import/lieferungen?pruefen=false", files={"datei": ("l.csv", csv, "text/csv")}).json()
    assert r["zeilen"][0]["fehler"] == [] and r["zeilen"][0]["aktion"] == "neu"
    assert haus["c"].get("/api/lieferungen").json()[0]["uhrzeit"] == "08:05"
    wb = Workbook()
    wb.active.append(["Irgendwas"])
    puffer = io.BytesIO()
    wb.save(puffer)
    assert haus["c"].post("/api/import/lieferungen", files={"datei": ("x.xlsx", puffer.getvalue(), "application/octet-stream")}).json()["detail"]["code"] == "spalten_fehlen"


def test_auswertung_excel(haus):
    lieferung(haus, ladung=[{"wagentyp_id": haus["wt"]["Wäschewagen"]["id"], "anzahl": 4}])
    r = haus["c"].get(f"/api/export/auswertung.xlsx?datum={FREITAG}")
    wb = load_workbook(io.BytesIO(r.content))
    assert wb.sheetnames[:4] == ["Übersicht", "Engpässe", "Fahrten", "Auslastung"]
    assert wb["Fahrten"].max_row == 5


def test_karte_pdf(haus):
    c = haus["c"]
    dok = c.post("/api/dokumente", files={"datei": ("p.pdf", pdf_bytes([(2500, 1000)]), "application/pdf")}).json()
    c.put(f"/api/stockwerke/{haus['ug']}/plan", json={"dokument_id": dok["id"], "seite": 1})
    lieferung(haus)
    r = c.get(f"/api/export/karte/{haus['ug']}.pdf?datum={FREITAG}&von=07:00&bis=09:00")
    assert r.status_code == 200 and r.content[:5] == b"%PDF-"
    doc = pymupdf.open(stream=r.content)
    text = doc[0].get_text()
    assert "Rampe" in text and "Logistik Map" in text and "1 Fahrten im Zeitfenster" in text
    assert c.get(f"/api/export/karte/{haus['og']}.pdf").json()["detail"]["code"] == "kein_plan"


def test_plan_wechsel_behaelt_massstab(haus):
    c = haus["c"]
    dok = c.post("/api/dokumente", files={"datei": ("p.pdf", pdf_bytes([(2500, 1000), (2500, 1000)]), "application/pdf")}).json()
    c.put(f"/api/stockwerke/{haus['ug']}/plan", json={"dokument_id": dok["id"], "seite": 1})
    r = c.put(f"/api/stockwerke/{haus['ug']}/plan", json={"dokument_id": dok["id"], "seite": 2}).json()
    assert r["inhalt_vorhanden"] is True
    assert c.get(f"/api/stockwerke/{haus['ug']}").json()["meter_pro_punkt"] == 0.05


def test_planer_darf_lieferungen_aber_kein_netz(haus, app):
    from contextlib import nullcontext

    from fastapi.testclient import TestClient

    haus["c"].post("/api/benutzer", json={"benutzername": "planer", "passwort": "planer123", "rolle": "planer"})
    with nullcontext(TestClient(app)) as p:
        p.post("/api/anmelden", json={"benutzername": "planer", "passwort": "planer123"})
        assert p.post("/api/lieferungen", json={"name": "x", "transportart_id": haus["ta"]["FTS"]["id"], "start_id": haus["rampe"],
                                                "ziel_id": haus["lager"], "uhrzeit": "09:00"}).status_code == 200
        assert p.post("/api/knoten", json={"stockwerk_id": haus["ug"], "x": 1, "y": 1}).status_code == 403
        assert p.post("/api/szenarien", json={"name": "Test"}).status_code == 200
