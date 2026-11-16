import os

import pymupdf
import pytest
from fastapi.testclient import TestClient

from logistikmap.config import Pfade
from logistikmap.server import erstelle_app

# Oberflächentests im Browser nur auf Wunsch (E2E=1), sie brauchen Playwright und einen Browser
collect_ignore = [] if os.environ.get("E2E") else ["e2e"]

ADMIN = {"benutzername": "admin", "anzeigename": "Admin", "passwort": "geheim123"}


@pytest.fixture
def pfade(tmp_path):
    return Pfade(tmp_path / "daten")


@pytest.fixture
def app(pfade):
    return erstelle_app(pfade)


@pytest.fixture
def client(app):
    with TestClient(app) as c:
        yield c


@pytest.fixture
def admin(client):
    r = client.post("/api/ersteinrichtung", json=ADMIN)
    assert r.status_code == 200, r.text
    return client


def pdf_bytes(seiten=((842, 595),)) -> bytes:
    doc = pymupdf.open()
    for i, (b, h) in enumerate(seiten):
        page = doc.new_page(width=b, height=h)
        page.draw_rect(pymupdf.Rect(20, 20, b - 20, h - 20), color=(0, 0, 0), width=2)
        page.insert_text((40, 60), f"Ebene {i}", fontsize=24)
    data = doc.tobytes()
    doc.close()
    return data
