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
    page.get_by_role("button", name="Strecken zeichnen").click()
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
    ws.append([None, "Wäsche", "Wäscherei", "Versorgung", "Materialtransportdienst", "Rampe", "Lager", "08:00", "", 10,
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


def test_erste_schritte(angemeldet, haus):
    page, c, og = angemeldet, haus["c"], haus["og"]
    # Nach der Anmeldung landet man auf „Erste Schritte“, solange die Einrichtung nicht fertig ist
    page.wait_for_url("**/#/start")
    page.wait_for_selector(".schritt.naechster")
    assert page.locator(".schritt.naechster h3").inner_text() == "Bundesland festlegen"
    assert page.locator("#navigation .nav-marke").inner_text().strip().isdigit()
    # Bundesland bestätigen → nächster Schritt rückt nach
    page.locator("#schritt-bundesland").get_by_role("button", name="Übernehmen").click()
    page.wait_for_selector("#schritt-bundesland.status-erledigt")
    # Punkt ohne Weg wird erkannt, „Beheben“ springt auf die Karte und wählt ihn aus
    kueche = c.post("knoten", json={"stockwerk_id": og, "x": 300, "y": 700, "art": "ziel", "name": "Küche"}).json()["id"]
    page.reload()
    problem = page.locator("#schritt-karte .probleme li", has_text="Küche")
    problem.get_by_role("link", name="Beheben").click()
    page.wait_for_url(f"**/#/karte/{og}/bearbeiten")
    page.wait_for_selector(".eigenschaften:not([hidden])")
    assert page.locator(".eigenschaften input").first.input_value() == "Küche"
    screenshot(page, "erste-schritte-sprung")
    # Stammdaten bestätigen
    page.goto(f"{haus['basis']}/#/start")
    page.locator("#schritt-stammdaten").get_by_role("button", name="Werte passen").click()
    page.wait_for_function("!document.querySelector('#schritt-stammdaten button')")
    assert kueche


def test_produktion_anlegen_und_auswerten(angemeldet, haus):
    """Punkt anklicken → Produktion anlegen → Rückstau in Auswertung und Ablauf sehen."""
    page, c = angemeldet, haus["c"]
    c.put(f"knoten/{haus['rampe']}", json={"art": "produktion", "name": "Küche"})
    fts = next(t for t in c.get("stammdaten").json()["transportarten"] if t["name"] == "FTS")
    c.put(f"transportarten/{fts['id']}", json={**fts, "anzahl": 1, "schichten": []})
    # vom Punkt auf der Karte aus
    page.goto(f"{haus['basis']}/#/karte/{haus['ug']}/bearbeiten")
    karte_bereit(page)
    page.mouse.click(*bildschirm(page, 200, 500))
    page.get_by_role("link", name="+ Produktion anlegen").click()
    dlg = page.locator("dialog[open]")

    def feld(name):  # genau dieses Feld – die Hilfetexte nennen auch andere
        return dlg.locator(f"label.feld:has(> span:text-is('{name}'))").locator("input, select").first

    feld("Bezeichnung").fill("Frühstück")
    feld("Was wird fertig?").select_option(label="Speisenwagen")
    feld("Takt (Minuten)").fill("10")
    feld("Stellplätze").fill("2")
    feld("Transportart").select_option(label="FTS")
    dlg.locator(".ladung select").select_option(str(haus["lager"]))
    dlg.locator(".ladung input").fill("31")
    assert "Ergibt 10 Wagen" in dlg.locator(".produktion-vorschau").inner_text()
    dlg.get_by_role("button", name="Takt für 31 Wagen anpassen").click()
    assert "Ergibt 31 Wagen" in dlg.locator(".produktion-vorschau").inner_text()
    feld("Abholung").select_option("menge")
    assert feld("ab wie vielen Wagen").is_visible() and not feld("Uhrzeiten").is_visible()
    feld("ab wie vielen Wagen").fill("3")
    dlg.get_by_role("button", name="Speichern").click()  # mehr als Stellplätze: Server lehnt ab, Dialog bleibt offen
    page.wait_for_selector(".dialog-fehler:not([hidden])")
    feld("ab wie vielen Wagen").fill("2")
    dlg.get_by_role("button", name="täglich").click()
    feld("Feiertage und Sondertage").select_option("auch")
    screenshot(page, "produktion-dialog")
    dlg.get_by_role("button", name="Speichern").click()
    page.wait_for_selector("table.tabelle >> text=Frühstück")
    screenshot(page, "produktion-liste")
    p = c.get("produktionen").json()[0]
    assert p["gesamt"] == 31 and p["takt"] == 3 and p["stellplaetze"] == 2 and p["abholung"]["menge"] == 2
    # Auswertung: steht, Kennzahl und Bild
    page.goto(f"{haus['basis']}/#/auswertung/2026-06-05")
    page.wait_for_selector(".produktion-karte.steht svg.produktion-verlauf rect.steht")
    assert "Stellplätze: Frühstück" in page.locator(".engpaesse").inner_text()
    page.locator(".produktion-karte a").click()
    page.wait_for_selector(".aufzug-status.produktion")
    screenshot(page, "produktion-ablauf")
    # am Handy: nichts ragt seitlich heraus
    page.set_viewport_size({"width": 390, "height": 844})
    page.goto(f"{haus['basis']}/#/auswertung/2026-06-05")
    page.wait_for_selector(".produktion-karte")
    assert page.evaluate("document.documentElement.scrollWidth") <= 390
    page.locator(".produktion-karte").scroll_into_view_if_needed()
    screenshot(page, "produktion-handy")
    page.goto(f"{haus['basis']}/#/lieferungen/produktion")
    page.get_by_role("button", name="Produktion anlegen").click()
    page.wait_for_selector("dialog[open] .lieferungsformular")
    zu_breit = page.evaluate("""(() => { const d = document.querySelector('dialog[open]'); const r = d.getBoundingClientRect().left + d.clientWidth;
        return d.scrollWidth <= d.clientWidth ? [] : [...d.querySelectorAll('*')].filter(e => e.getBoundingClientRect().right > r).map(e => e.outerHTML.slice(0, 80)); })()""")
    assert not zu_breit, zu_breit
    screenshot(page, "produktion-handy-dialog")
    page.get_by_role("button", name="Abbrechen").click()
    page.set_viewport_size({"width": 1400, "height": 900})
    # „?“ führt auf der Seite Produktion zum eigenen Kapitel
    page.goto(f"{haus['basis']}/#/lieferungen/produktion")
    page.wait_for_selector("table.tabelle >> text=Frühstück")
    page.click("#hilfe-knopf")
    page.wait_for_url("**/#/hilfe/produktion")


def test_produktion_mindestbedarf_und_szenario(angemeldet, haus):
    page, c = angemeldet, haus["c"]
    sd = c.get("stammdaten").json()
    fts = next(t for t in sd["transportarten"] if t["name"] == "FTS")
    c.put(f"transportarten/{fts['id']}", json={**fts, "anzahl": 1, "schichten": []})
    r = c.post("produktionen", json={
        "name": "Küche", "knoten_id": haus["rampe"], "transportart_id": fts["id"], "wagentyp_id": sd["wagentypen"][0]["id"],
        "von": "06:30", "bis": "07:30", "takt": 4, "stellplaetze": 3, "verteilung": [{"ziel_id": haus["lager"], "anzahl": 1}],
        "regel": {"wochentage": [1, 2, 3, 4, 5]}})
    assert r.status_code == 200, r.text
    page.goto(f"{haus['basis']}/#/auswertung/2026-06-05")
    page.get_by_role("link", name="Mindestbedarf").click()
    page.get_by_label("Was?").select_option(f"produktion:{r.json()['id']}")
    assert page.get_by_label("darf höchstens stehen (Min.)").input_value() == "0"
    page.get_by_role("button", name="Berechnen").click()
    page.wait_for_selector(".bedarf-ergebnis", timeout=20000)
    screenshot(page, "produktion-bedarf")
    sid = c.post("szenarien", json={"name": "Mehr Platz", "aenderungen": {}}).json()["id"]
    page.goto(f"{haus['basis']}/#/szenarien/{sid}")
    reihe = page.locator("tr", has_text="Küche").filter(has=page.locator("input[type=time]")).first
    reihe.locator("input[type=number]").nth(2).fill("12")
    page.get_by_role("button", name="Speichern").click()
    page.wait_for_selector(".meldung")
    assert c.get("szenarien").json()[0]["aenderungen"] == {"produktionen": {str(r.json()["id"]): {"stellplaetze": 12}}}
