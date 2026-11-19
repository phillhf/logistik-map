"""Oberflächentests im echten Browser (Playwright).

Startet Logistik Map mit leerem Datenordner auf einem freien Port und legt ein kleines Testhaus an:
UG mit Rampe, Flur, Aufzug und Raum, 2. OG mit Lager. Lokal wird Edge verwendet, in GitHub Actions Chromium.

Aufruf: pytest tests/e2e  (mit SCREENSHOTS=1 landen Kontrollbilder in test-results/bilder)
"""

from __future__ import annotations

import os
import socket
import sys
import threading
import time
from pathlib import Path

import httpx
import pytest
import uvicorn

import importlib.util

_spec = importlib.util.spec_from_file_location("tests_gemeinsam", Path(__file__).resolve().parent.parent / "conftest.py")
_gemeinsam = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_gemeinsam)
pdf_bytes = _gemeinsam.pdf_bytes

from logistikmap.config import Pfade  # noqa: E402
from logistikmap.server import erstelle_app  # noqa: E402

ADMIN = {"benutzername": "admin", "passwort": "e2e-geheim-123"}


def _freier_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def browser_type_launch_args(browser_type_launch_args):
    # lokal (Windows ohne heruntergeladenes Chromium) den installierten Edge nehmen
    if sys.platform == "win32" and not os.environ.get("CI"):
        return {**browser_type_launch_args, "channel": "msedge"}
    return browser_type_launch_args


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    return {**browser_context_args, "viewport": {"width": 1400, "height": 900}, "locale": "de-DE"}


@pytest.fixture
def server(tmp_path):
    port = _freier_port()
    app = erstelle_app(Pfade(tmp_path / "daten"))
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
    yield {"basis": basis, "app": app, "pfade": tmp_path / "daten"}
    srv.should_exit = True
    thread.join(timeout=10)


@pytest.fixture
def haus(server):
    """Testhaus über die Schnittstelle anlegen. Gibt Server-Infos, API-Client und IDs zurück."""
    c = httpx.Client(base_url=server["basis"] + "/api/", timeout=30)
    assert c.post("ersteinrichtung", json={**ADMIN, "anzeigename": "Test"}).status_code == 200
    gid = c.post("gebaeudeteile", json={"name": "Haus A", "kuerzel": "A"}).json()["id"]
    ug = c.post("stockwerke", json={"gebaeudeteil_id": gid, "name": "Untergeschoss", "ebene": -1}).json()["id"]
    og = c.post("stockwerke", json={"gebaeudeteil_id": gid, "name": "2. OG", "ebene": 2}).json()["id"]
    dok = c.post("dokumente", files={"datei": ("plan.pdf", pdf_bytes([(1600, 1000), (1600, 1000)]), "application/pdf")}).json()["id"]
    for sid, seite in ((ug, 1), (og, 2)):
        c.put(f"stockwerke/{sid}/plan", json={"dokument_id": dok, "seite": seite})
        c.put(f"stockwerke/{sid}/massstab", json={"meter_pro_punkt": 0.05})
    for _ in range(200):
        if all(s["plan"]["status"] == "fertig" for t in c.get("gebaeude").json() for s in t["stockwerke"]):
            break
        time.sleep(0.1)
    auf = c.post("aufzuege", json={"name": "Aufzug 1", "art": "aufzug", "plaetze": 2, "fahrzeit_etage": 5, "tuerzeit": 10,
                                   "raeumzeit": 20, "anfahrt": 15, "transportarten": []}).json()["id"]

    def knoten(sid, x, y, art="weg", name="", **kw):
        return c.post("knoten", json={"stockwerk_id": sid, "x": x, "y": y, "art": art, "name": name, **kw}).json()["id"]

    rampe = knoten(ug, 200, 500, "start", "Rampe")
    flur_a = knoten(ug, 400, 500)
    flur_b = knoten(ug, 1200, 500)
    a_ug = knoten(ug, 1200, 300, "aufzug", aufzug_id=auf)
    a_og = knoten(og, 1200, 300, "aufzug", aufzug_id=auf)
    lager = knoten(og, 600, 300, "ziel", "Lager")
    for a, b in ((rampe, flur_a), (flur_a, flur_b), (flur_b, a_ug), (a_og, lager)):
        c.post("kanten", json={"von": a, "nach": b})
    raum = c.post("flaechen", json={"stockwerk_id": ug, "art": "raum", "name": "Warenannahme",
                                    "punkte": [[100, 600], [500, 600], [500, 900], [100, 900]]}).json()["id"]
    yield {**server, "c": c, "ug": ug, "og": og, "rampe": rampe, "flur_a": flur_a, "flur_b": flur_b, "lager": lager, "raum": raum}
    c.close()


@pytest.fixture
def angemeldet(page, haus):
    page.goto(haus["basis"] + "/")
    page.get_by_label("Benutzername").fill(ADMIN["benutzername"])
    page.get_by_label("Passwort").fill(ADMIN["passwort"])
    page.get_by_role("button", name="Anmelden").click()
    page.wait_for_selector("#navigation a")
    return page
