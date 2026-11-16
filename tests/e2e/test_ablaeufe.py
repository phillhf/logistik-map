"""Abläufe in der Oberfläche, die sich nur im Browser sinnvoll prüfen lassen."""

import io
import zipfile

from openpyxl import load_workbook

from hilfen import bildschirm, karte_bereit, screenshot


def test_weg_zeichnen_teilt_flur_und_rueckgaengig(angemeldet, haus):
    page, c, ug = angemeldet, haus["c"], haus["ug"]
    vorher = c.get(f"stockwerke/{ug}/netz").json()
    page.goto(f"{haus['basis']}/#/karte/{ug}/bearbeiten")
    karte_bereit(page)
    page.get_by_role("button", name="Weg zeichnen").click()
    # Klick mitten auf den Flur → Flur wird geteilt, neuer Wegpunkt
    page.mouse.click(*bildschirm(page, 800, 500))
    page.wait_for_timeout(500)
    # zweiter Klick darunter → neuer Punkt und Wegstück (fast senkrecht → wird gerade gezogen)
    page.mouse.click(*bildschirm(page, 805, 800))
    page.wait_for_timeout(500)
    page.keyboard.press("Escape")
    nachher = c.get(f"stockwerke/{ug}/netz").json()
    assert len(nachher["knoten"]) == len(vorher["knoten"]) + 2
    assert len(nachher["kanten"]) == len(vorher["kanten"]) + 2
    neu = [k for k in nachher["knoten"] if k["id"] not in {x["id"] for x in vorher["knoten"]}]
    assert {round(k["x"]) for k in neu} == {800}, "zweiter Punkt wurde nicht senkrecht ausgerichtet"
    screenshot(page, "editor")
    # Strg+Z nimmt den zweiten Klick als einen Schritt zurück, noch einmal den ersten
    page.keyboard.press("Escape")
    page.keyboard.press("Control+z")
    page.wait_for_timeout(500)
    assert len(c.get(f"stockwerke/{ug}/netz").json()["kanten"]) == len(vorher["kanten"]) + 1
    page.keyboard.press("Control+z")
    page.wait_for_timeout(500)
    zurueck = c.get(f"stockwerke/{ug}/netz").json()
    assert len(zurueck["kanten"]) == len(vorher["kanten"]) and len(zurueck["knoten"]) == len(vorher["knoten"])


def test_raumecke_ziehen(angemeldet, haus):
    page, c, ug = angemeldet, haus["c"], haus["ug"]
    page.goto(f"{haus['basis']}/#/karte/{ug}/bearbeiten")
    karte_bereit(page)
    page.mouse.click(*bildschirm(page, 300, 800))  # Raum auswählen
    page.wait_for_selector(".leaflet-marker-icon.ecke:not(.mitte)")
    x, y = bildschirm(page, 500, 900)  # Ecke unten rechts
    page.mouse.move(x, y)
    page.mouse.down()
    page.mouse.move(x + 20, y + 10, steps=5)
    page.mouse.move(x + 40, y + 20, steps=5)
    page.mouse.up()
    page.wait_for_timeout(600)
    punkte = next(f for f in c.get(f"stockwerke/{ug}/netz").json()["flaechen"] if f["id"] == haus["raum"])["punkte"]
    assert punkte[2][0] > 520 and punkte[2][1] > 910, punkte
    assert punkte[0] == [100, 600]


def test_ausrichten(angemeldet, haus):
    page, c, ug = angemeldet, haus["c"], haus["ug"]
    page.goto(f"{haus['basis']}/#/karte/{ug}/bearbeiten")
    karte_bereit(page)
    page.get_by_role("button", name="Ausrichten").click()
    # Rampe (200,500) → (250,520), Flurpunkt (1200,500) → (1250,520): reine Verschiebung um (50, 20)
    for alt, neu in (((200, 500), (250, 520)), ((1200, 500), (1250, 520))):
        page.mouse.click(*bildschirm(page, *alt))
        page.wait_for_timeout(200)
        page.mouse.click(*bildschirm(page, *neu))
        page.wait_for_timeout(200)
    page.get_by_role("button", name="Anwenden (2 Paare)").click()
    page.wait_for_timeout(800)
    rampe = next(k for k in c.get(f"stockwerke/{ug}/netz").json()["knoten"] if k["id"] == haus["rampe"])
    assert abs(rampe["x"] - 250) < 3 and abs(rampe["y"] - 520) < 3, rampe


def test_import_dialog(angemeldet, haus):
    page, c = angemeldet, haus["c"]
    wb = load_workbook(io.BytesIO(c.get("export/lieferungen.xlsx").content))
    ws = wb["Lieferungen"]
    ws.append([None, "Wäsche", "Wäscherei", "Versorgung", "Materialtransportdienst", "Rampe", "Lager", "08:00", "",
               "4 Wäschewagen", "Mo-Fr", "nicht", "", "", "leer", "", "", "ja", ""])
    puffer = io.BytesIO()
    wb.save(puffer)
    page.goto(f"{haus['basis']}/#/lieferungen")
    with page.expect_file_chooser() as fc:
        page.get_by_role("button", name="⤒ Importieren").click()
    fc.value.set_files(files=[{"name": "lieferungen.xlsx", "mimeType": "application/octet-stream", "buffer": puffer.getvalue()}])
    page.wait_for_selector("dialog[open] .import")
    assert "1 neu" in page.locator("dialog[open]").inner_text()
    page.get_by_role("button", name="Übernehmen").click()
    page.wait_for_selector("td >> text=Wäsche")
    assert [l["name"] for l in c.get("lieferungen").json()] == ["Wäsche"]
    screenshot(page, "lieferungen")


def test_sicherung_einspielen(angemeldet, haus):
    page, c = angemeldet, haus["c"]
    sicherung = c.get("sicherung").content
    assert zipfile.ZipFile(io.BytesIO(sicherung)).namelist()
    c.post("gebaeudeteile", json={"name": "Wird verworfen"})
    page.goto(f"{haus['basis']}/#/einstellungen")
    with page.expect_file_chooser() as fc:
        page.get_by_role("button", name="Sicherung einspielen").click()
    fc.value.set_files(files=[{"name": "sicherung.zip", "mimeType": "application/zip", "buffer": sicherung}])
    page.locator("dialog[open]").get_by_role("button", name="Sicherung einspielen").click()
    page.wait_for_timeout(2500)  # Seite lädt neu
    assert [t["name"] for t in c.get("gebaeude").json()] == ["Haus A"]


def test_ablauf_und_auswertung(angemeldet, haus):
    page, c = angemeldet, haus["c"]
    ta = {t["name"]: t["id"] for t in c.get("stammdaten").json()["transportarten"]}
    wt = {w["name"]: w["id"] for w in c.get("stammdaten").json()["wagentypen"]}
    c.post("lieferungen", json={"name": "Wäsche", "transportart_id": ta["Materialtransportdienst"], "start_id": haus["rampe"],
                                "ziel_id": haus["lager"], "uhrzeit": "08:00", "ladung": [{"wagentyp_id": wt["Wäschewagen"], "anzahl": 8}],
                                "regel": {"wochentage": [1, 2, 3, 4, 5, 6, 7], "feiertage": "auch"}})
    page.goto(f"{haus['basis']}/#/karte/{haus['ug']}/ablauf/2026-06-05/08:03")
    karte_bereit(page)
    page.wait_for_selector(".fahrzeug")
    assert "8 Fahrten" in page.locator(".ablaufinfo").inner_text()
    screenshot(page, "ablauf")
    page.goto(f"{haus['basis']}/#/auswertung/2026-06-05")
    page.wait_for_selector(".kennzahl")
    assert page.locator(".engpass").count() >= 1
    screenshot(page, "auswertung")
