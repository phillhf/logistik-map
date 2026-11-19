"""Bilder für die README: baut ein frei erfundenes „Musterklinikum“ auf und fotografiert die Oberfläche.

Alles hier ist erfunden – Plan, Räume, Lieferanten. Echte Pläne gehören nie ins Repo.

Aufruf (braucht requirements-e2e.txt, lokal mit Edge):
    .venv\\Scripts\\python werkzeuge\\screenshots.py
Die Bilder landen in docs/screenshots/.
"""

from __future__ import annotations

import socket
import sys
import tempfile
import threading
import time
from pathlib import Path

import httpx
import pymupdf
import uvicorn

WURZEL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WURZEL))

from logistikmap.config import Pfade  # noqa: E402
from logistikmap.server import erstelle_app  # noqa: E402

ZIEL = WURZEL / "docs" / "screenshots"
DATUM = "2026-11-19"  # ein Donnerstag ohne Feiertag
ADMIN = {"benutzername": "admin", "anzeigename": "Anna Admin", "passwort": "screenshot-demo-123"}
WERKTAGE = {"wochentage": [1, 2, 3, 4, 5]}

# --------------------------------------------------------------------------- Plan (A3 quer, M 1:200)
B, H = 1190.55, 841.89
FLUR_Y = 420  # Mitte des Hauptflurs
OBEN = [(60, 330), (330, 620), (620, 840), (840, 1130)]  # Räume über dem Flur (rechts: bis 330, darunter Aufzüge)
STOCKWERKE = {
    "Untergeschoss": (-1, ["Warenannahme", "Zentrallager", "Apotheke", "Bettenaufbereitung"],
                      ["Wäscheversorgung", "Küche", "Technik", "Entsorgung"]),
    "Erdgeschoss": (0, ["Notaufnahme", "Radiologie", "Station E1", "Station E2"],
                    ["Ambulanzen", "Eingangshalle", "Cafeteria", "Station E3"]),
    "2. Obergeschoss": (2, ["OP-Bereich", "Sterilgutversorgung", "Intensivstation", "Station 2A"],
                        ["Station 2B", "Station 2C", "Aufwachraum", "Station 2D"]),
}


def tuer_x(x0: float, x1: float, y0: float) -> float:
    """Tür bzw. Anschlusspunkt: Raummitte; oben rechts neben dem Aufzugskern."""
    return 1105 if x0 == 840 and y0 < FLUR_Y else (x0 + x1) / 2


def raeume(oben: list[str], unten: list[str]) -> list[tuple[str, tuple[float, float, float, float]]]:
    r = []
    for (x0, x1), name in zip(OBEN, oben):
        r.append((name, (x0, 90, x1, 330 if x0 == 840 else 400)))
    for (x0, x1), name in zip(OBEN, unten):
        r.append((name, (x0, 440, x1, 770)))
    return r


def plan_pdf() -> bytes:
    doc = pymupdf.open()
    wand, flur, text, grau = (0.25, 0.27, 0.3), (0.93, 0.94, 0.95), (0.2, 0.22, 0.25), (0.55, 0.57, 0.6)
    for name, (ebene, oben, unten) in STOCKWERKE.items():
        s = doc.new_page(width=B, height=H)
        s.draw_rect(pymupdf.Rect(60, 400, 1130, 440), color=None, fill=flur)
        for raum, (x0, y0, x1, y1) in raeume(oben, unten):
            s.draw_rect(pymupdf.Rect(x0, y0, x1, y1), color=wand, width=2.2)
            # Tür zum Flur
            ty = y1 if y0 < FLUR_Y else y0
            mx = tuer_x(x0, x1, y0)
            s.draw_line(pymupdf.Point(mx - 14, ty), pymupdf.Point(mx + 14, ty), color=(1, 1, 1), width=3)
            s.insert_textbox(pymupdf.Rect(x0 + 8, (y0 + y1) / 2 - 10, x1 - 8, (y0 + y1) / 2 + 12), raum,
                             fontsize=13, color=text, align=pymupdf.TEXT_ALIGN_CENTER)
        # Aufzugskern und Treppe
        for x0, beschriftung in ((850, "A"), (950, "B"), (1020, "Treppe")):
            breite = 40 if beschriftung != "Treppe" else 55
            s.draw_rect(pymupdf.Rect(x0, 340, x0 + breite, 395), color=wand, width=1.6, fill=(0.88, 0.9, 0.93))
            s.insert_textbox(pymupdf.Rect(x0, 358, x0 + breite, 376), beschriftung, fontsize=9, color=text,
                             align=pymupdf.TEXT_ALIGN_CENTER)
        s.draw_rect(pymupdf.Rect(60, 90, 1130, 770), color=wand, width=3.5)
        if ebene == -1:  # Rampe mit zwei Toren
            s.draw_rect(pymupdf.Rect(18, 150, 60, 360), color=wand, width=1.6, fill=(0.97, 0.95, 0.9))
            for y in (190, 300):
                s.draw_line(pymupdf.Point(60, y - 22), pymupdf.Point(60, y + 22), color=(0.9, 0.55, 0.1), width=5)
            s.insert_text(pymupdf.Point(18, 140), "Rampe", fontsize=10, color=text)
        s.insert_text(pymupdf.Point(60, 805), f"Musterklinikum – {name}", fontsize=14, color=text)
        s.insert_text(pymupdf.Point(60, 823), "Frei erfundener Beispielplan  ·  M 1:200", fontsize=9, color=grau)
        s.draw_line(pymupdf.Point(1030, 805), pymupdf.Point(1030 + 10 / (0.0254 / 72 * 200), 805), color=text, width=2)
        s.insert_text(pymupdf.Point(1030, 822), "10 m", fontsize=9, color=text)
    daten = doc.tobytes()
    doc.close()
    return daten


# --------------------------------------------------------------------------- Server und Daten
def freier_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def aufbauen(c: httpx.Client) -> dict:
    assert c.post("ersteinrichtung", json=ADMIN).status_code == 200
    c.put("einstellungen", json={"bundesland": "NW"})
    c.put(f"standorte/{c.get('standorte').json()['aktuell']}", json={"name": "Musterklinikum"})

    gid = c.post("gebaeudeteile", json={"name": "Hauptgebäude", "kuerzel": "H"}).json()["id"]
    dok = c.post("dokumente", files={"datei": ("musterklinikum.pdf", plan_pdf(), "application/pdf")}).json()["id"]
    sw = {}
    for nr, (name, (ebene, _, _)) in enumerate(STOCKWERKE.items(), start=1):
        sid = c.post("stockwerke", json={"gebaeudeteil_id": gid, "name": name, "ebene": ebene}).json()["id"]
        c.put(f"stockwerke/{sid}/plan", json={"dokument_id": dok, "seite": nr})
        c.put(f"stockwerke/{sid}/massstab", json={"verhaeltnis": 200})
        sw[name] = sid
    for _ in range(600):
        if all(s["plan"]["status"] == "fertig" for t in c.get("gebaeude").json() for s in t["stockwerke"]):
            break
        time.sleep(0.2)

    sd = c.get("stammdaten").json()
    ta = {t["name"]: t for t in sd["transportarten"]}
    wt = {w["name"]: w["id"] for w in sd["wagentypen"]}
    for name, werte in (("FTS", {"anzahl": 5}), ("Materialtransportdienst", {"anzahl": 5})):
        c.put(f"transportarten/{ta[name]['id']}", json={**{k: ta[name][k] for k in (
            "name", "farbe", "geschwindigkeit", "ladezeit", "entladezeit", "wagen_pro_fahrt", "aufzug_exklusiv", "treppe")}, **werte})
    grundlast = [{"von": "07:00", "bis": "09:00", "prozent": 25, "wochentage": [1, 2, 3, 4, 5]}]
    auf = {n: c.post("aufzuege", json={"name": n, "art": "aufzug", "plaetze": 2, "fahrzeit_etage": 6, "tuerzeit": 12,
                                         "raeumzeit": 20, "anfahrt": 20, "transportarten": [], "grundlast": grundlast}).json()["id"]
           for n in ("Lastenaufzug", "Bettenaufzug")}

    def knoten(sid, x, y, art="weg", name="", **kw):
        r = c.post("knoten", json={"stockwerk_id": sid, "x": x, "y": y, "art": art, "name": name, **kw})
        assert r.status_code == 200, r.text
        return r.json()["id"]

    def kante(a, b):
        assert c.post("kanten", json={"von": a, "nach": b}).status_code == 200

    punkte: dict[str, int] = {}
    quellen = {"Zentrallager", "Apotheke", "Küche", "Wäscheversorgung", "Sterilgutversorgung"}
    for name, (ebene, oben, unten) in STOCKWERKE.items():
        sid = sw[name]
        xs = [195, 475, 730, 870, 970, 1105] + ([100] if ebene == -1 else [])
        flur = {x: knoten(sid, x, FLUR_Y) for x in sorted(xs)}
        reihe = sorted(flur)
        for a, b in zip(reihe, reihe[1:]):
            kante(flur[a], flur[b])
        for aname, x in (("Lastenaufzug", 870), ("Bettenaufzug", 970)):
            kante(knoten(sid, x, 380, "aufzug", aufzug_id=auf[aname]), flur[x])
        for raum, (x0, y0, x1, y1) in raeume(oben, unten):
            if raum in ("Technik", "Eingangshalle", "Cafeteria", "Warenannahme"):
                continue
            mx = tuer_x(x0, x1, y0)
            y = 385 if y0 < FLUR_Y else 455
            art = "start" if raum in quellen else "ziel"
            punkte[raum] = knoten(sid, mx, y, art, raum)
            kante(punkte[raum], flur[min(flur, key=lambda fx: abs(fx - mx))])
        if ebene == -1:
            tor = knoten(sid, 40, 245, "tor", "Rampe", kapazitaet=2, minuten_je_einheit=2, minuten_je_einheit_bis=4)
            ecke = knoten(sid, 100, 245)
            kante(tor, ecke)
            kante(ecke, flur[100])
            punkte["Rampe"] = tor

    def lieferung(zeit, name, start, ziel, art, ladung, anzahl, lieferant="", richtung="versorgung", streuung=0):
        r = c.post("lieferungen", json={
            "name": name, "lieferant": lieferant, "richtung": richtung, "transportart_id": ta[art]["id"],
            "start_id": punkte[start], "ziel_id": punkte[ziel], "uhrzeit": zeit, "streuung": streuung,
            "ladung": [{"wagentyp_id": wt[ladung], "anzahl": anzahl}], "regel": WERKTAGE, "rueckweg": {"modus": "leer"}})
        assert r.status_code == 200, r.text

    mtd = "Materialtransportdienst"
    lieferung("06:00", "Lebensmittel", "Rampe", "Küche", mtd, "Palette", 4, "Lebensmittel-Großhandel", streuung=20)
    lieferung("06:15", "Medizinprodukte", "Rampe", "Zentrallager", mtd, "Palette", 6, "Medizin-Logistik", streuung=30)
    lieferung("06:20", "Saubere Wäsche", "Rampe", "Wäscheversorgung", mtd, "Rollcontainer", 8, "Textilservice", streuung=15)
    lieferung("06:30", "Arzneimittel", "Rampe", "Apotheke", mtd, "Palette", 2, "Pharmagroßhandel", streuung=10)
    lieferung("07:00", "Büro- und Verbrauchsmaterial", "Rampe", "Zentrallager", mtd, "Palette", 2, "Bürobedarf", streuung=20)
    for zeit, station, n in (("07:15", "Station E1", 3), ("07:15", "Station E2", 3), ("07:18", "Station E3", 2),
                             ("07:20", "Station 2A", 3), ("07:20", "Station 2B", 3), ("07:22", "Station 2C", 2),
                             ("07:24", "Station 2D", 2), ("07:25", "Intensivstation", 2)):
        lieferung(zeit, f"Frühstück {station}", "Küche", station, "FTS", "Speisenwagen", n)
    lieferung("07:40", "Modulversorgung 2C", "Zentrallager", "Station 2C", mtd, "Rollcontainer", 2)
    lieferung("07:45", "Wäsche 2A", "Wäscheversorgung", "Station 2A", mtd, "Wäschewagen", 2)
    lieferung("07:50", "Wäsche E3", "Wäscheversorgung", "Station E3", mtd, "Wäschewagen", 2)
    lieferung("08:00", "Arzneimittel Intensiv", "Apotheke", "Intensivstation", mtd, "Rollcontainer", 1)
    lieferung("08:00", "Sterilgut OP", "Sterilgutversorgung", "OP-Bereich", mtd, "Rollcontainer", 3)
    lieferung("08:30", "Notfallmedikamente", "Apotheke", "Notaufnahme", mtd, "Rollcontainer", 1)
    lieferung("09:00", "Abfall 2B", "Station 2B", "Entsorgung", mtd, "Rollcontainer", 2, richtung="entsorgung")
    lieferung("09:15", "Abfall E1", "Station E1", "Entsorgung", mtd, "Rollcontainer", 2, richtung="entsorgung")
    lieferung("10:00", "Betten zur Aufbereitung", "Station 2A", "Bettenaufbereitung", mtd, "Bett", 2, richtung="intern")
    c.post("einrichtung/bestaetigen", json={"schritt": "stammdaten"})
    c.post("einrichtung/bestaetigen", json={"schritt": "bundesland"})
    return sw


# --------------------------------------------------------------------------- Fotos
def oeffnen(seite, basis: str, adresse: str) -> None:
    """Seite unter der Adresse öffnen. Direkt nach der Anmeldung springt die App noch auf ihre
    Startseite – deshalb prüfen und notfalls noch einmal öffnen."""
    ziel = basis + "/" + adresse
    for _ in range(5):
        seite.goto(ziel)
        seite.reload()  # nur der Teil hinter # ändert sich – neu laden, damit die Seite genau dort startet
        seite.wait_for_load_state("networkidle")
        time.sleep(0.5)
        if seite.url == ziel:
            return
    raise RuntimeError(f"Adresse {adresse} lässt sich nicht öffnen (steht bei {seite.url})")


def fotografieren(basis: str, sw: dict) -> None:
    from playwright.sync_api import sync_playwright

    ZIEL.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge" if sys.platform == "win32" else None)
        ctx = browser.new_context(viewport={"width": 1440, "height": 900}, locale="de-DE", device_scale_factor=1)
        seite = ctx.new_page()
        seite.goto(basis + "/")
        seite.get_by_label("Benutzername").fill(ADMIN["benutzername"])
        seite.get_by_label("Passwort").fill(ADMIN["passwort"])
        seite.get_by_role("button", name="Anmelden").click()
        seite.wait_for_selector("#navigation a")

        def foto(name: str, adresse: str, warten: str | None = None, vorher=None, pause: float = 1.2):
            oeffnen(seite, basis, adresse)
            if vorher:
                vorher()
            if warten:
                try:
                    seite.wait_for_selector(warten, timeout=30000)
                except Exception:
                    seite.screenshot(path=str(ZIEL / f"FEHLER-{name}.png"))
                    print("   FEHLER", name, seite.url)
                    raise
            seite.wait_for_load_state("networkidle")
            time.sleep(pause)
            seite.screenshot(path=str(ZIEL / f"{name}.png"))
            print("  ", name)

        ug, eg, og = sw["Untergeschoss"], sw["Erdgeschoss"], sw["2. Obergeschoss"]
        seite.evaluate("localStorage.setItem('lm_ablauf_farbe', 'transportart')")
        foto("ablauf", f"#/karte/{ug}/ablauf/{DATUM}/07:24", ".fz")
        foto("editor", f"#/karte/{ug}/bearbeiten", ".leaflet-tile-loaded")
        foto("auswertung", f"#/auswertung/{DATUM}", ".kennzahlen")
        foto("lieferungen", "#/lieferungen", "table")
        foto("start", "#/start", ".schritt, .karte-box")
        foto("hilfe", "#/hilfe/auswertung", ".hilfe-text section")

        def streuung():
            seite.wait_for_selector(".kennzahlen")
            seite.get_by_role("link", name="Streuung").click()
            seite.get_by_role("button", name="Berechnen").click()

        foto("streuung", f"#/auswertung/{DATUM}", ".kennzahlen .kennzahl strong", vorher=streuung)
        ctx.close()

        # Handy: Ablauf und aufgeklapptes Menü
        handy = browser.new_context(viewport={"width": 390, "height": 844}, locale="de-DE", device_scale_factor=2,
                                    is_mobile=True, has_touch=True, storage_state=None)
        s = handy.new_page()
        s.goto(basis + "/")
        s.get_by_label("Benutzername").fill(ADMIN["benutzername"])
        s.get_by_label("Passwort").fill(ADMIN["passwort"])
        s.get_by_role("button", name="Anmelden").click()
        s.wait_for_selector("#menue-knopf")
        oeffnen(s, basis, f"#/karte/{ug}/ablauf/{DATUM}/07:24")
        try:
            s.wait_for_selector(".fz", timeout=30000)
        except Exception:
            s.screenshot(path=str(ZIEL / "FEHLER-handy.png"))
            print("   FEHLER handy", s.url)
            raise
        # näher heran: Küche, Flur und Aufzüge
        s.evaluate("(() => { const k = window.__logistikKarte.karte; k.setView([440, 640], k.getZoom() + 0.75, { animate: false }); })()")
        s.wait_for_load_state("networkidle")
        time.sleep(1.2)
        s.screenshot(path=str(ZIEL / "handy-ablauf.png"))
        s.click("#menue-knopf")
        time.sleep(0.4)
        s.screenshot(path=str(ZIEL / "handy-menue.png"))
        print("   handy-ablauf, handy-menue")
        handy.close()
        browser.close()


def main() -> None:
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        port = freier_port()
        app = erstelle_app(Pfade(Path(tmp) / "daten"))
        srv = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
        thread = threading.Thread(target=srv.run, daemon=True)
        thread.start()
        basis = f"http://127.0.0.1:{port}"
        for _ in range(100):
            try:
                httpx.get(f"{basis}/api/status", timeout=1)
                break
            except httpx.HTTPError:
                time.sleep(0.05)
        print("Musterklinikum aufbauen …")
        with httpx.Client(base_url=basis + "/api/", timeout=60) as c:
            sw = aufbauen(c)
        print("Fotos …")
        try:
            fotografieren(basis, sw)
        finally:
            srv.should_exit = True
            thread.join(timeout=10)


if __name__ == "__main__":
    main()
